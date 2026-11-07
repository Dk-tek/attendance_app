"""Authenticated mobile attendance and durable, idempotent tracking ingestion."""
from datetime import datetime, timedelta, timezone
import os
import uuid

from fastapi import HTTPException, Request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from pydantic import BaseModel, Field, ConfigDict, field_validator
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


def timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return value.astimezone(timezone.utc)


def as_utc(value):
    # Mongo returns UTC dates without tzinfo unless tz_aware is configured.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Event(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: str = Field(min_length=16, max_length=100)
    employee_id: str = Field(min_length=1, max_length=200)
    org_id: str = Field(min_length=1, max_length=200)
    timestamp: datetime

    @field_validator('timestamp', mode='before')
    @classmethod
    def aware_timestamp(cls, value):
        result = timestamp(value)
        if result > datetime.now(timezone.utc) + timedelta(minutes=2):
            raise ValueError('Timestamp is in the future')
        return result


class AttendanceEvent(Event):
    attendance_type: str
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    face_token: str
    session_id: str | None = None


class LocationEvent(Event):
    session_id: str = Field(min_length=1, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    accuracy: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    tracking_status: str = 'ok'
    remark: str = Field(default='', max_length=500)


class MobileAPI:
    def __init__(self, context, secret):
        self.c = context
        self.signer = URLSafeTimedSerializer(secret, salt='mobile-session-v1')
        self.face_signer = URLSafeTimedSerializer(secret, salt='attendance-face-v1')
        self.ttl = int(os.getenv('MOBILE_TOKEN_TTL_SECONDS', '604800'))

    def issue_token(self, role, employee_id, org_id, email=None):
        return self.signer.dumps(dict(role=role, employee_id=employee_id, org_id=org_id, email=email))

    def identity(self, request: Request, admin=False):
        value = request.headers.get('authorization', '')
        try:
            if not value.startswith('Bearer '):
                raise BadSignature('Missing bearer token')
            who = self.signer.loads(value[7:], max_age=self.ttl)
        except (BadSignature, SignatureExpired):
            raise HTTPException(401, 'Session expired. Please log in again.')
        org = self.c['get_org_by_id'](who['org_id'])
        if not org or not org.get('is_active', False):
            raise HTTPException(403, 'Organization is inactive')
        if who['role'] == 'admin':
            user = self.c['admin_users_collection'].find_one({'org_id': who['org_id'], 'email': who['email']})
        else:
            user = self.c['users_collection'].find_one({'org_id': who['org_id'], 'employee_id': who['employee_id']})
        if not user or not user.get('is_active', True):
            raise HTTPException(403, 'Account is inactive')
        if admin and who['role'] != 'admin':
            raise HTTPException(403, 'Administrator access required')
        who['employee_name'] = user.get('employee_name') or user.get('name', '')
        return who

    def scope(self, who, org_id, employee_id=None, admin_allowed=True):
        if org_id != who['org_id'] or (employee_id and employee_id != who['employee_id'] and (not admin_allowed or who['role'] != 'admin')):
            raise HTTPException(403, 'Employee or organization does not match your session')

    def face_proof(self, who, employee_id):
        self.scope(who, who['org_id'], employee_id)
        return self.face_signer.dumps(dict(org_id=who['org_id'], employee_id=employee_id, actor=who['employee_id']))

    def settings(self, org_id, employee_id):
        settings = self.c['get_org_tracking_settings'](org_id)
        active = self.c['find_active_session'](org_id, employee_id)
        if active:
            settings['auto_checkout_enabled'] = active.get('auto_checkout_enabled', True)
        return settings

    def state(self, who):
        self.c['auto_checkout_due_sessions']()
        return dict(success=True, user_type=who['role'], employee_id=who['employee_id'], employee_name=who['employee_name'], org_id=who['org_id'], tracking_settings=self.settings(who['org_id'], who['employee_id']), **self.c['get_attendance_state'](who['org_id'], who['employee_id']))

    def record_transition(self, session, kind):
        prefix = 'check_in' if kind == 'check_in' else 'check_out'
        event_id = session[f'{prefix}_event_id']
        record = dict(event_id=event_id, session_id=session['session_id'], org_id=session['org_id'], employee_id=session['employee_id'], employee_name=session['employee_name'], attendance_type=kind, timestamp=as_utc(session[f'{prefix}_time']).isoformat())
        record.update(session.get(f'{prefix}_location', {}))
        if kind == 'check_out':
            record.update(checkout_source=session.get('checkout_source', 'manual'), remark=session.get('checkout_remark', ''))
        self.c['attendance_collection'].update_one({'event_id': event_id}, {'$setOnInsert': record}, upsert=True)

    def attendance(self, request, event):
        who = self.identity(request)
        self.scope(who, event.org_id, event.employee_id)
        if event.attendance_type not in ('check_in', 'check_out'):
            raise HTTPException(422, 'Invalid attendance type')
        try:
            proof = self.face_signer.loads(event.face_token, max_age=120)
        except (BadSignature, SignatureExpired):
            raise HTTPException(401, 'Face verification expired. Scan again.')
        if proof != dict(org_id=event.org_id, employee_id=event.employee_id, actor=who['employee_id']):
            raise HTTPException(403, 'Face verification does not match employee')
        self.c['auto_checkout_due_sessions']()
        sessions = self.c['attendance_sessions_collection']
        scope = dict(org_id=event.org_id, employee_id=event.employee_id)
        prefix = event.attendance_type
        existing = sessions.find_one({**scope, f'{prefix}_event_id': event.event_id})
        if existing:
            self.record_transition(existing, prefix)
            return dict(success=True, **self.c['get_attendance_state'](event.org_id, event.employee_id), tracking_settings=self.settings(event.org_id, event.employee_id))
        user = self.c['users_collection'].find_one(scope) or self.c['collection'].find_one(scope)
        if event.employee_id == who['employee_id']:
            name = who['employee_name']
        elif not user or not user.get('is_active', True):
            raise HTTPException(404, 'Employee not found or inactive')
        else:
            name = user['employee_name']
        now = datetime.now(timezone.utc)
        if abs((now - event.timestamp).total_seconds()) > 300:
            raise HTTPException(422, 'Attendance requires a current timestamp')
        if prefix == 'check_in':
            settings = self.c['get_org_tracking_settings'](event.org_id)
            session = dict(**scope, session_id=uuid.uuid4().hex, employee_name=name, status='active', check_in_time=now, check_in_event_id=event.event_id, check_in_location=dict(latitude=event.latitude, longitude=event.longitude), expected_checkout_at=now+timedelta(hours=settings['tracking_timeout_hours']), created_at=now, updated_at=now, **settings)
            try:
                sessions.insert_one(session)
            except DuplicateKeyError:
                raise HTTPException(409, 'Employee is already checked in. Refresh attendance state.')
        else:
            if not event.session_id:
                raise HTTPException(422, 'session_id is required for checkout')
            session = sessions.find_one_and_update({**scope, 'session_id': event.session_id, 'status': 'active'}, {'$set': dict(status='closed', check_out_time=now, check_out_event_id=event.event_id, check_out_location=dict(latitude=event.latitude, longitude=event.longitude), checkout_source='manual', updated_at=now)}, return_document=ReturnDocument.AFTER)
            if not session:
                raise HTTPException(409, 'No matching active attendance session. Refresh attendance state.')
        self.record_transition(session, prefix)
        return dict(success=True, **self.c['get_attendance_state'](event.org_id, event.employee_id), tracking_settings=self.settings(event.org_id, event.employee_id))

    def location(self, request, event):
        who = self.identity(request)
        # Phone location always belongs to its logged-in employee, including admins.
        self.scope(who, event.org_id, event.employee_id, admin_allowed=False)
        if event.tracking_status not in ('ok', 'failed'):
            raise HTTPException(422, 'Invalid tracking status')
        if event.tracking_status == 'ok' and (event.latitude is None or event.longitude is None):
            raise HTTPException(422, 'GPS coordinates are required')
        if event.tracking_status == 'failed' and not event.remark.strip():
            raise HTTPException(422, 'Failure remark is required')
        self.c['auto_checkout_due_sessions']()
        session = self.c['attendance_sessions_collection'].find_one(dict(session_id=event.session_id, org_id=event.org_id, employee_id=event.employee_id))
        if not session:
            raise HTTPException(409, 'Unknown attendance session')
        end = session.get('check_out_time')
        if event.timestamp < as_utc(session['check_in_time']) or (end and event.timestamp > as_utc(end)):
            raise HTTPException(409, 'Location was captured outside the attendance session')
        if session.get('auto_checkout_enabled') and event.timestamp > as_utc(session['expected_checkout_at']):
            raise HTTPException(409, 'Attendance session has expired')
        body = event.model_dump(exclude_none=True)
        if event.tracking_status == 'failed':
            body.pop('latitude', None)
            body.pop('longitude', None)
        body.update(timestamp=event.timestamp.isoformat(), employee_name=who['employee_name'], received_at=datetime.now(timezone.utc))
        self.c['location_collection'].update_one({'org_id': event.org_id, 'employee_id': event.employee_id, 'event_id': event.event_id}, {'$setOnInsert': body}, upsert=True)
        return dict(success=True, message='Location saved')

    def install(self, app):
        @app.get('/mobile/session')
        def session(request: Request):
            return self.state(self.identity(request))

        @app.post('/attendance')
        def attendance(request: Request, event: AttendanceEvent):
            return self.attendance(request, event)

        @app.post('/location-track')
        def location(request: Request, event: LocationEvent):
            return self.location(request, event)
