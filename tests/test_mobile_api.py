import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import uuid

import mongomock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo import ReturnDocument

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mobile_api import MobileAPI, as_utc


@pytest.fixture
def env():
    db = mongomock.MongoClient().attendance
    context = dict(datetime=datetime, timedelta=timedelta, timezone=timezone, ReturnDocument=ReturnDocument, as_utc=as_utc)
    for name in ['attendance_collection', 'location_collection', 'attendance_sessions_collection', 'users_collection', 'admin_users_collection', 'collection']:
        context[name] = db[name]
    db.users_collection.insert_one(dict(employee_id='employee', employee_name='Employee', org_id='org', is_active=True))
    db.admin_users_collection.insert_one(dict(email='admin@example.com', org_id='org', is_active=True, name='Admin'))
    org = dict(org_id='org', is_active=True)
    context['get_org_by_id'] = lambda value: org if value == 'org' else None
    context['get_org_tracking_settings'] = lambda value: dict(auto_checkout_enabled=True, tracking_timeout_hours=4, tracking_interval_minutes=30)
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'attendance.py').read_text())
    names = {'utc_now', 'parse_record_timestamp', 'format_api_timestamp', 'find_active_session', 'get_attendance_state', 'auto_checkout_due_sessions'}
    module = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
    exec(compile(module, 'attendance_functions', 'exec'), context)
    mobile = MobileAPI(context, 'test-secret-that-is-long-enough-for-testing')
    context['mobile'] = mobile
    db.attendance_sessions_collection.create_index([('org_id', 1), ('employee_id', 1)], unique=True, partialFilterExpression={'status': 'active'})
    db.attendance_collection.create_index('event_id', unique=True, sparse=True)
    db.location_collection.create_index([('org_id', 1), ('employee_id', 1), ('event_id', 1)], unique=True)
    app = FastAPI()
    mobile.install(app)
    client = TestClient(app)
    client.headers['Authorization'] = 'Bearer ' + mobile.issue_token('user', 'employee', 'org')
    return client, mobile, db, context, org


def attendance(mobile, kind='check_in', **kw):
    return dict(event_id=uuid.uuid4().hex, employee_id='employee', org_id='org', timestamp=datetime.now(timezone.utc).isoformat(), attendance_type=kind, latitude=12.9, longitude=77.6, face_token=mobile.face_proof(dict(org_id='org', employee_id='employee', role='user'), 'employee'), **kw)


def check_in(env):
    client, mobile, *_ = env
    response = client.post('/attendance', json=attendance(mobile))
    assert response.status_code == 200, response.text
    return response.json()['active_session_id']


def location(session_id, **kw):
    return dict(event_id=uuid.uuid4().hex, employee_id='employee', org_id='org', timestamp=datetime.now(timezone.utc).isoformat(), session_id=session_id, latitude=12.9, longitude=77.6) | kw


def test_requires_authentication(env):
    client, *_ = env
    client.headers.clear()
    assert client.get('/mobile/session').status_code == 401
    assert client.post('/location-track', json=location('x')).status_code == 401


def test_disabling_account_or_org_revokes_access(env):
    client, _, db, _, org = env
    org['is_active'] = False
    assert client.get('/mobile/session').status_code == 403
    org['is_active'] = True
    db.users_collection.update_one({}, {'$set': {'is_active': False}})
    assert client.get('/mobile/session').status_code == 403


def test_rejects_wrong_employee_and_org(env):
    client, *_ = env
    assert client.post('/location-track', json=location('x', employee_id='someone')).status_code == 403
    assert client.post('/location-track', json=location('x', org_id='other')).status_code == 403


def test_rejects_invalid_coordinates_and_unknown_session(env):
    client, *_ = env
    assert client.post('/location-track', json=location('x', latitude=999)).status_code == 422
    assert client.post('/location-track', json=location('x')).status_code == 409


def test_checkin_retry_is_idempotent_and_duplicate_action_conflicts(env):
    client, mobile, db, *_ = env
    body = attendance(mobile)
    assert client.post('/attendance', json=body).status_code == 200
    assert client.post('/attendance', json=body).status_code == 200
    assert client.post('/attendance', json=attendance(mobile)).status_code == 409
    assert db.attendance_collection.count_documents({}) == 1
    assert db.attendance_sessions_collection.count_documents({}) == 1


def test_checkout_requires_matching_session_and_is_idempotent(env):
    client, mobile, db, *_ = env
    sid = check_in(env)
    assert client.post('/attendance', json=attendance(mobile, 'check_out', session_id='wrong')).status_code == 409
    body = attendance(mobile, 'check_out', session_id=sid)
    assert client.post('/attendance', json=body).json()['is_checked_in'] is False
    assert client.post('/attendance', json=body).status_code == 200
    assert db.attendance_collection.count_documents({'attendance_type': 'check_out'}) == 1


def test_face_proof_required_and_bound_to_employee(env):
    client, mobile, *_ = env
    body = attendance(mobile)
    body['face_token'] = 'fake'
    assert client.post('/attendance', json=body).status_code == 401
    body = attendance(mobile)
    body['employee_id'] = 'someone'
    assert client.post('/attendance', json=body).status_code == 403


def test_gps_retry_and_offline_upload_after_checkout(env):
    client, mobile, db, *_ = env
    sid = check_in(env)
    body = location(sid)
    assert client.post('/attendance', json=attendance(mobile, 'check_out', session_id=sid)).status_code == 200
    assert client.post('/location-track', json=body).status_code == 200
    assert client.post('/location-track', json=body).status_code == 200
    assert db.location_collection.count_documents({}) == 1
    later = location(sid, timestamp=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat())
    assert client.post('/location-track', json=later).status_code == 409


def test_failure_events_are_stored_without_coordinates(env):
    client, _, db, *_ = env
    sid = check_in(env)
    body = location(sid, tracking_status='failed', remark='GPS disabled')
    assert client.post('/location-track', json=body).status_code == 200
    stored = db.location_collection.find_one({})
    assert 'latitude' not in stored
    assert stored['tracking_status'] == 'failed'
    assert client.post('/location-track', json=location(sid, tracking_status='failed')).status_code == 422


def test_timezone_required_and_utc_normalized(env):
    client, *_ = env
    sid = check_in(env)
    assert client.post('/location-track', json=location(sid, timestamp='2026-11-07T10:00:00')).status_code == 422
    body = location(sid, timestamp=datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat())
    assert client.post('/location-track', json=body).status_code == 200
    assert env[2].location_collection.find_one({})['timestamp'].endswith('+00:00')


def test_auto_checkout_is_once_and_uses_deadline(env):
    client, _, db, context, _ = env
    sid = check_in(env)
    deadline = datetime.now(timezone.utc)-timedelta(seconds=1)
    db.attendance_sessions_collection.update_one({'session_id': sid}, {'$set': {'expected_checkout_at': deadline}})
    context['auto_checkout_due_sessions']()
    context['auto_checkout_due_sessions']()
    assert client.get('/mobile/session').json()['is_checked_in'] is False
    records = list(db.attendance_collection.find({'attendance_type': 'check_out'}))
    assert len(records) == 1
    assert datetime.fromisoformat(records[0]['timestamp']) == as_utc(db.attendance_sessions_collection.find_one({})['expected_checkout_at'])
    assert client.post('/location-track', json=location(sid)).status_code == 409


def test_reconciles_crash_between_session_and_attendance_write(env):
    _, _, db, context, _ = env
    check_in(env)
    db.attendance_collection.delete_many({})
    context['auto_checkout_due_sessions']()
    assert db.attendance_collection.count_documents({'attendance_type': 'check_in'}) == 1


def test_admin_cannot_track_another_employees_phone(env):
    client, mobile, *_ = env
    sid = check_in(env)
    client.headers['Authorization'] = 'Bearer ' + mobile.issue_token('admin', 'admin', 'org', 'admin@example.com')
    assert client.post('/location-track', json=location(sid)).status_code == 403
