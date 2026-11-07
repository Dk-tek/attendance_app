"""Exercise attendance.py's actual route wiring without loading face models.
Only image-processing imports are stubbed; auth, routing and DB logic are real.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

import mongomock
import pymongo
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SESSION_SECRET', 'test-only-secret-long-enough-for-session-signing')
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setattr(pymongo, 'MongoClient', lambda *a, **kw: mongomock.MongoClient())
    source = Path(__file__).resolve().parents[1] / 'attendance.py'
    tree = ast.parse(source.read_text())
    heavy = {'cv2', 'mediapipe', 'numpy', 'onnxruntime', 'PIL', 'sklearn'}
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.Import) and any(alias.name.split('.')[0] in heavy for alias in node.names)
        or isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] in heavy
    )]
    namespace = {'np': SimpleNamespace(array=lambda *a, **kw: None, float32=None), 'mp': SimpleNamespace(solutions=SimpleNamespace(face_mesh=None))}
    exec(compile(tree, str(source), 'exec'), namespace)
    namespace['organizations_collection'].insert_one({'org_id': 'org', 'org_code': 'ORG', 'is_active': True})
    namespace['users_collection'].insert_one({'employee_id': 'employee', 'employee_name': 'Employee', 'email': 'employee@example.com', 'org_id': 'org', 'password_hash': namespace['hash_password']('password'), 'is_active': True})
    with TestClient(namespace['app']) as client:
        yield client, namespace


def test_login_token_and_actual_mobile_session_route(server):
    client, _ = server
    response = client.post('/login', json={'username': 'employee@example.com', 'password': 'password'})
    assert response.status_code == 200
    assert response.json()['success'] is True
    token = response.json()['access_token']
    client.headers['Authorization'] = 'Bearer ' + token
    assert client.get('/mobile/session').json()['employee_id'] == 'employee'
    assert client.get('/attendance-record/employee').status_code == 200
    assert client.get('/attendance-record/someone').status_code == 403
    assert client.get('/list').status_code == 403
    assert client.post('/edit/employee', data={'employee_name': 'changed'}).status_code == 403
    assert client.delete('/delete/employee').status_code == 403


def test_actual_face_and_history_routes_require_login(server):
    client, _ = server
    assert client.get('/list').status_code == 401
    assert client.get('/attendance-record/employee').status_code == 401
    assert client.post('/authenticate', files={'live_image': ('face.jpg', b'not-an-image', 'image/jpeg')}, data={'org_id': 'org'}).status_code == 401
    assert client.post('/enroll-face', files={'file': ('face.jpg', b'not-an-image', 'image/jpeg')}, data={'org_id': 'org', 'employee_id': 'employee', 'employee_name': 'Employee'}).status_code == 401


def test_date_filters_use_same_ist_day_as_display(server):
    _, ns = server
    dt = ns['to_date']('2026-11-08')
    instant = '2026-11-07T20:00:00+00:00'
    assert ns['is_timestamp_in_range'](instant, exact_date=dt)
    assert ns['format_display_timestamp'](instant).startswith('08-11-2026')


def test_web_session_is_revoked_when_user_is_disabled(server):
    client, ns = server
    assert client.post('/api/auth/login', json={'username': 'employee@example.com', 'password': 'password', 'role': 'user'}).status_code == 200
    ns['users_collection'].update_one({'employee_id': 'employee'}, {'$set': {'is_active': False}})
    assert client.get('/api/user/dashboard').status_code == 403
