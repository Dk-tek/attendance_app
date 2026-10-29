from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
import numpy as np
import cv2
from PIL import Image, ImageOps
import onnxruntime as ort
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime, timezone
import os
import io
import threading
import anyio
import mediapipe as mp
from pymongo import MongoClient, ASCENDING
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ONNX_PATH            = os.getenv("ONNX_PATH", "w600k_r50.onnx")
DOCDB_URI            = os.getenv(
    "DOCDB_URI",
    "mongodb://localhost:27017/"  # override with DocumentDB cluster URI in production
)
DOCDB_TLS_CA         = os.getenv("DOCDB_TLS_CA", "global-bundle.pem")  # Amazon CA bundle
DB_NAME              = os.getenv("DB_NAME", "face_auth1")
COLLECTION_NAME      = os.getenv("COLLECTION_NAME", "employees")
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.60"))
MAX_FILE_BYTES       = int(os.getenv("MAX_FILE_BYTES", str(10 * 1024 * 1024)))  # 10 MB
ALLOWED_ORIGINS      = os.getenv("ALLOWED_ORIGINS", "*").split(",")
API_KEY              = os.getenv("API_KEY", "")  

# Face quality thresholds
MIN_FACE_SIZE_PX   = 80
MIN_BLUR_SCORE     = 80.0
MIN_BRIGHTNESS     = 40
MAX_BRIGHTNESS     = 220
MAX_TILT_ANGLE_DEG = 25

# ---------------------------------------------------------------------------
# MediaPipe
# ---------------------------------------------------------------------------
MP_FACE_MESH = mp.solutions.face_mesh

LEFT_IRIS   = 468
RIGHT_IRIS  = 473
NOSE_TIP    = 1
LEFT_MOUTH  = 61
RIGHT_MOUTH = 291

ARCFACE_DST = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)

# ---------------------------------------------------------------------------
# ONNX
# ---------------------------------------------------------------------------
_ort_opts = ort.SessionOptions()
_ort_opts.intra_op_num_threads = 2
session    = ort.InferenceSession(ONNX_PATH, sess_options=_ort_opts)
input_name = session.get_inputs()[0].name

# ---------------------------------------------------------------------------
# AWS DocumentDB
# ---------------------------------------------------------------------------
_docdb_kwargs = (
    {"tls": True, "tlsCAFile": DOCDB_TLS_CA, "retryWrites": False}
    if os.path.isfile(DOCDB_TLS_CA)
    else {"retryWrites": False}
)
_mongo_client = MongoClient(
    DOCDB_URI,
    maxPoolSize=20,
    serverSelectionTimeoutMS=5000,
    **_docdb_kwargs,
)
db         = _mongo_client[DB_NAME]
collection = db[COLLECTION_NAME]

# ---------------------------------------------------------------------------
# In-memory embedding cache
# ---------------------------------------------------------------------------
_cache_lock: threading.Lock       = threading.Lock()
_embedding_cache: dict[str, list] = {}


def _load_cache(org_id: str | None = None) -> None:
    query = {"org_id": org_id} if org_id else {}
    docs  = list(collection.find(
        query,
        {"_id": 0, "employee_id": 1, "employee_name": 1, "org_id": 1, "embedding": 1},
    ))
    for d in docs:
        d["embedding"] = np.array(d["embedding"], dtype=np.float32)
    cache_key = org_id if org_id else "_all_"
    with _cache_lock:
        _embedding_cache[cache_key] = docs
    logger.info("Cache loaded: %d records for org_id=%r", len(docs), cache_key)


def _invalidate_cache() -> None:
    with _cache_lock:
        _embedding_cache.clear()


def _get_cached(org_id: str | None) -> list[dict]:
    cache_key = org_id if org_id else "_all_"
    with _cache_lock:
        if cache_key in _embedding_cache:
            return list(_embedding_cache[cache_key])
    _load_cache(org_id)
    with _cache_lock:
        return list(_embedding_cache.get(cache_key, []))


# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    collection.create_index([("employee_id", ASCENDING)], unique=True)
    collection.create_index([("org_id", ASCENDING)])
    await anyio.to_thread.run_sync(lambda: _load_cache(None))
    logger.info("Startup complete — %d employees cached",
                len(_embedding_cache.get("_all_", [])))
    yield
    _mongo_client.close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Optional API-key guard
# ---------------------------------------------------------------------------
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: str | None = Depends(_api_key_header)) -> None:
    if API_KEY and key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def read_image_from_bytes(data: bytes) -> np.ndarray | None:
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        arr = np.array(img.convert("RGB"))
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    except Exception as exc:
        logger.warning("read_image_from_bytes failed: %s", exc)
        return None


def preprocess_face(face_bgr: np.ndarray) -> np.ndarray:
    face = cv2.resize(face_bgr, (112, 112))
    face = face.astype(np.float32) / 255.0
    face = (face - 0.5) / 0.5
    face = np.transpose(face, (2, 0, 1))
    return np.expand_dims(face, axis=0)


def l2_normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v / norm if norm > 1e-10 else v


# ---------------------------------------------------------------------------
# Face quality gate
# ---------------------------------------------------------------------------
def check_face_quality(face_bgr: np.ndarray) -> tuple[bool, str]:
    h, w = face_bgr.shape[:2]

    if h < MIN_FACE_SIZE_PX or w < MIN_FACE_SIZE_PX:
        return False, f"Face too small ({w}x{h}px, need {MIN_FACE_SIZE_PX}px minimum)"

    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)

    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    if blur_score < MIN_BLUR_SCORE:
        return False, f"Face too blurry (score={blur_score:.1f}, need >={MIN_BLUR_SCORE})"

    brightness = float(gray.mean())
    if brightness < MIN_BRIGHTNESS:
        return False, f"Face too dark (brightness={brightness:.1f})"
    if brightness > MAX_BRIGHTNESS:
        return False, f"Face overexposed (brightness={brightness:.1f})"

    return True, ""


# ---------------------------------------------------------------------------
# Core: 5-point similarity-transform alignment → 112x112 ArcFace crop
# ---------------------------------------------------------------------------
def _get_aligned_face(
    image_bgr: np.ndarray,
    landmarks,
    img_h: int,
    img_w: int,
) -> tuple[np.ndarray | None, str]:
    lm = landmarks.landmark

    lx = lm[LEFT_IRIS].x * img_w;  ly = lm[LEFT_IRIS].y * img_h
    rx = lm[RIGHT_IRIS].x * img_w; ry = lm[RIGHT_IRIS].y * img_h
    angle = np.degrees(np.arctan2(ry - ly, rx - lx))
    if abs(angle) > MAX_TILT_ANGLE_DEG:
        return None, (
            f"Face too tilted ({angle:.1f}°, max ±{MAX_TILT_ANGLE_DEG}°) — "
            "please hold the camera straight"
        )

    src = np.array([
        [lx, ly],
        [rx, ry],
        [lm[NOSE_TIP].x    * img_w, lm[NOSE_TIP].y    * img_h],
        [lm[LEFT_MOUTH].x  * img_w, lm[LEFT_MOUTH].y  * img_h],
        [lm[RIGHT_MOUTH].x * img_w, lm[RIGHT_MOUTH].y * img_h],
    ], dtype=np.float32)

    M, _ = cv2.estimateAffinePartial2D(src, ARCFACE_DST, method=cv2.LMEDS)
    if M is None:
        return None, "Face alignment transform failed"

    aligned = cv2.warpAffine(image_bgr, M, (112, 112),
                              flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REFLECT)
    return aligned, ""


def extract_mesh_faces(
    image_bgr: np.ndarray,
    max_faces: int = 10,
) -> tuple[list[np.ndarray], list[str]]:
    img_h, img_w = image_bgr.shape[:2]
    rgb          = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    crops:      list[np.ndarray] = []
    rejections: list[str]        = []

    with MP_FACE_MESH.FaceMesh(
        static_image_mode=True,
        max_num_faces=max_faces,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as face_mesh:
        results = face_mesh.process(rgb)
        if not results.multi_face_landmarks:
            return [], []

        for i, landmarks in enumerate(results.multi_face_landmarks):
            aligned, reason = _get_aligned_face(image_bgr, landmarks, img_h, img_w)
            if aligned is not None:
                crops.append(aligned)
            else:
                logger.warning("Alignment rejected (face %d): %s", i, reason)
                rejections.append(reason)

    return crops, rejections


# ---------------------------------------------------------------------------
# Embedding: quality gate → ONNX → L2 normalize
# ---------------------------------------------------------------------------
def embedding_from_mesh_crop(
    face_bgr: np.ndarray,
) -> tuple[np.ndarray | None, str]:
    ok, reason = check_face_quality(face_bgr)
    if not ok:
        return None, reason

    try:
        face_rgb  = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        processed = preprocess_face(face_rgb)
        raw       = session.run(None, {input_name: processed})[0].flatten()
        return l2_normalize(raw), ""
    except Exception as exc:
        logger.error("embedding_from_mesh_crop: %s", exc)
        return None, "Embedding extraction failed"


def get_embedding_single(
    image_np: np.ndarray,
) -> tuple[np.ndarray | None, str | None]:
    crops, tilt_rejections = extract_mesh_faces(image_np, max_faces=5)
    if not crops:
        reason = tilt_rejections[0] if tilt_rejections else "No face detected"
        return None, reason
    if len(crops) > 1:
        return None, "Multiple faces detected — use a single-face photo"

    emb, reason = embedding_from_mesh_crop(crops[0])
    if emb is None:
        return None, reason
    return emb, None


def get_all_embeddings(
    image_np: np.ndarray,
) -> tuple[list[np.ndarray], list[str]]:
    crops, rejections = extract_mesh_faces(image_np, max_faces=10)
    embeddings: list[np.ndarray] = []

    for crop in crops:
        emb, reason = embedding_from_mesh_crop(crop)
        if emb is not None:
            embeddings.append(emb)
        else:
            rejections.append(reason)

    return embeddings, rejections


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    try:
        _mongo_client.admin.command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "status":           "ok" if db_ok else "degraded",
        "db":               "ok" if db_ok else "unreachable",
        "cached_employees": sum(len(v) for v in _embedding_cache.values()),
        "threshold":        SIMILARITY_THRESHOLD,
    }


@app.post("/enroll-face", dependencies=[Depends(verify_api_key)])
async def enroll_face(
    employee_id:   str        = Form(...),
    employee_name: str        = Form(...),
    org_id:        str        = Form(...),
    file:          UploadFile = File(...),
):
    image_bytes = await file.read(MAX_FILE_BYTES + 1)
    if len(image_bytes) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file")

    image_np = await anyio.to_thread.run_sync(read_image_from_bytes, image_bytes)
    if image_np is None:
        raise HTTPException(status_code=400, detail="Failed to decode image")

    embedding, err = await anyio.to_thread.run_sync(
        lambda: get_embedding_single(image_np)
    )
    if err:
        raise HTTPException(status_code=400, detail=err)

    await anyio.to_thread.run_sync(
        lambda: collection.update_one(
            {"employee_id": employee_id},
            {"$set": {
                "employee_id":   employee_id,
                "employee_name": employee_name,
                "org_id":        org_id,
                "embedding":     embedding.tolist(),
                "model_version": os.path.basename(ONNX_PATH),
                "updated_at":    datetime.now(timezone.utc),
            }},
            upsert=True,
        )
    )
    _invalidate_cache()

    return {
        "success":     True,
        "message":     "Employee enrolled successfully",
        "employee_id": employee_id,
        "org_id":      org_id,
    }


@app.post("/authenticate", dependencies=[Depends(verify_api_key)])
async def authenticate(
    live_image: UploadFile = File(...),
    org_id:     str | None = Form(None),
):
    image_bytes = await live_image.read(MAX_FILE_BYTES + 1)
    if len(image_bytes) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    if not image_bytes:
        return JSONResponse(status_code=400,
                            content={"authenticated": False, "error": "Empty image"})

    image_np = await anyio.to_thread.run_sync(read_image_from_bytes, image_bytes)
    if image_np is None:
        return JSONResponse(status_code=400,
                            content={"authenticated": False, "error": "Failed to decode image"})

    live_embeddings, rejections = await anyio.to_thread.run_sync(
        lambda: get_all_embeddings(image_np)
    )

    if not live_embeddings:
        reason = rejections[0] if rejections else "No face detected"
        return JSONResponse(
            status_code=422,
            content={"authenticated": False, "error": reason},
        )

    employees = await anyio.to_thread.run_sync(lambda: _get_cached(org_id))
    if not employees:
        return {"authenticated": False, "error": "No enrolled employees found"}

    db_matrix  = np.stack([e["embedding"] for e in employees])
    best_score = -1.0
    best_match = None

    for live_emb in live_embeddings:
        scores = cosine_similarity(live_emb.reshape(1, -1), db_matrix)[0]
        idx    = int(np.argmax(scores))
        if scores[idx] > best_score:
            best_score = float(scores[idx])
            best_match = employees[idx]

    if best_score >= SIMILARITY_THRESHOLD:
        return {
            "authenticated":    True,
            "employee_id":      best_match["employee_id"],
            "employee_name":    best_match["employee_name"],
            "org_id":           best_match.get("org_id"),
            "similarity_score": round(best_score, 4),
            "faces_detected":   len(live_embeddings),
        }

    return {
        "authenticated":    False,
        "similarity_score": round(best_score, 4),
        "faces_detected":   len(live_embeddings),
        "error":            "Face does not match any enrolled employee",
    }
