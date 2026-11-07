# Attendance tracking rollout

Deploy the mobile app and backend together. Older clients do not send bearer tokens, face proofs, event IDs, or session IDs and will be rejected by the secured endpoints. Sign in again after upgrading.

## Server setup

- Set `SESSION_SECRET` to a random, private value of at least 32 characters. Startup deliberately rejects a missing/short value. Keep it identical across workers and restarts. Rotation invalidates existing mobile and web sessions.
- Set a strong `SUPERADMIN_PASSWORD`; the built-in default password was removed.
- Serve production over HTTPS. Session cookies are secure by default. For localhost HTTP development only, set `COOKIE_SECURE=false`.
- Run from `backend` with `uvicorn attendance:app`. `blurryonnxapicomplete.py` is a separate face-only server and is not the attendance application.
- MongoDB must support unique partial indexes. Startup creates one active session per organization/employee, unique session IDs, and idempotency indexes. Back up existing data first. If legacy duplicate active sessions or duplicate session IDs exist, resolve those records before starting; the application does not silently delete or rewrite historical attendance.
- Legacy timestamps without timezone information are ambiguous. New writes require timezone-aware timestamps and are normalized to UTC. Back up and migrate legacy naive phone timestamps using the timezone of the device that produced them; do not blindly assume they were UTC. Old Mongo date fields may also contain local wall-clock values written as UTC by the old client. Resolve old active sessions before rollout if their deadlines are incorrect.
- API display times and date filters use IST; stored instants use UTC. New manual attendance uses server receipt time after checking client clock skew (five-minute tolerance). Face proofs last two minutes; signed mobile login tokens last seven days by default (`MOBILE_TOKEN_TTL_SECONDS`). Disabled users and organizations are rejected on each request.

## Tracking behavior

Android uses a separate foreground-service Flutter engine with a persistent location notification. It starts while the app is visible after login/check-in, polls server attendance state, and captures at the configured interval. The manifest declares a location service and its required permissions. Boot auto-start is disabled: reopen the app after a phone restart. Android force-stop, revoked permissions, battery restrictions, and manufacturer task killers can interrupt execution; the app restores the saved session when opened again. A late restart records an interruption event rather than inventing GPS coordinates.

iOS uses Core Location background mode with the background location indicator and an active location stream. Exact periodic execution is OS-controlled. User termination/reboot requires reopening. Validate on a signed physical iPhone; this Linux environment cannot build iOS. The app does not claim uninterrupted tracking when the OS prevents execution.

Credentials and queued location events use platform secure storage. Events keep original UTC capture times and IDs until accepted. HTTP retries are deduplicated on the server. Late uploads for closed sessions are accepted only if captured during the session. Rejected events are retained locally for diagnosis; pending queues are isolated by server, organization, and employee. Queue capacity is 10,000 events; a full queue produces an explicit status error. Reinstalling/clearing app data can erase pending events.

A GPS error creates a failed event with a remark and no coordinates. A network outage with usable GPS queues real coordinates. Mock, stale (over two minutes), and inaccurate (over 100m) readings are rejected on the client. These checks do not provide hardware-backed proof against a modified client.

Admin face scanning may record another employee's attendance, but never associates the admin phone's periodic GPS with that employee. Employees must use their own login/device for their location trail. Face matching provides a short-lived signed proof; it is not a liveness/anti-spoofing system.

Automatic checkout uses an atomic session transition, then an idempotent attendance upsert. Reconciliation repairs interrupted attendance writes from the authoritative session on subsequent polls. This avoids requiring MongoDB transactions on standalone installations.

## Verification

```sh
python -m pip install -r requirements-test.txt
python -m pytest tests -q
cd frontend
# Use Node 22.12+ (the build tools require a modern Node version).
npm ci
node --test src/utils/mapPoints.test.js
npm run build
```

From the Flutter root:

```sh
flutter pub get
flutter test
flutter analyze --no-fatal-infos
flutter build apk --debug
```

Physical-device acceptance before rollout:

1. Use two employees and two organizations. Verify cross-employee/cross-org writes fail, including an admin phone trying to upload another person's GPS.
2. Check in; confirm one attendance session, immediate GPS upload, and a persistent Android notification. Check that the next point follows the configured interval.
3. Lock the screen and switch apps for at least two intervals. Verify capture timestamps and database points, not just the UI status.
4. Turn off the network, collect points, reopen, then reconnect. Confirm original timestamps and no duplicate events.
5. Deny location permission or disable GPS. Verify a visible error and a failed GPS event when execution/network permit it.
6. Check out manually and via the server deadline. Verify no later locations are collected. Confirm delayed points captured before checkout still synchronize.
7. Force-stop/reboot/reopen. Verify session recovery and interruption reporting. Do not expect collection during an OS force-stop.
8. Change interval, disable the user/organization, expire the token, and revoke permissions while tracking. Verify errors and stopping behavior.
9. Verify dashboard refresh, IST date boundaries, failure details, and absence of false markers at (0,0).
