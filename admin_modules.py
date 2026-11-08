"""Additive admin APIs. Reuse the application's cookie roles and tenant scope."""
from datetime import datetime, timezone
from typing import Literal
import re
import uuid

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


class EmployeeUpdate(BaseModel):
    employee_name: str = Field(min_length=1, max_length=160)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(default="", max_length=256)


class PolicyUpdate(BaseModel):
    content: str = Field(max_length=100000)
    revision: int = Field(ge=0)
    publish: bool = False


class PlanInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(pattern=r"^[a-z0-9_-]{2,40}$")
    description: str = Field(default="", max_length=2000)
    price_minor: int = Field(ge=0, le=10000000000)
    currency: Literal['INR', 'USD', 'EUR', 'GBP'] = 'INR'
    billing_cycle: Literal["monthly", "yearly"]
    max_users: int = Field(ge=1, le=10000000)
    per_user_price_minor: int = Field(default=0, ge=0, le=10000000000)
    is_active: bool = True


class AssignmentInput(BaseModel):
    plan_id: str
    starts_at: datetime
    ends_at: datetime | None = None
    price_minor: int | None = Field(default=None, ge=0, le=10000000000)
    per_user_price_minor: int | None = Field(default=None, ge=0, le=10000000000)


def plan_pricing(plan):
    """Existing flat-price plans remain valid, with a zero per-user charge."""
    return {k: v for k, v in {**plan, 'per_user_price_minor': plan.get('per_user_price_minor', 0)}.items()
            if k not in {'_id', 'features', 'storage_gb'}}


def build_subscription(db, payload):
    plan = db['subscription_plans'].find_one({'plan_id': payload.plan_id, 'is_active': True})
    if not plan:
        raise HTTPException(400, 'Choose an active plan')
    plan = plan_pricing(plan)
    start = payload.starts_at.replace(tzinfo=payload.starts_at.tzinfo or timezone.utc)
    end = payload.ends_at.replace(tzinfo=payload.ends_at.tzinfo or timezone.utc) if payload.ends_at else None
    if end and end <= start:
        raise HTTPException(400, 'End date must be after start date')
    if payload.price_minor is not None:
        plan['price_minor'] = payload.price_minor
    if payload.per_user_price_minor is not None:
        plan['per_user_price_minor'] = payload.per_user_price_minor
    return {'plan_id': plan['plan_id'], 'plan': plan, 'starts_at': start, 'ends_at': end,
            'updated_at': datetime.now(timezone.utc)}


def register_admin_modules(app, ns):
    db = ns['db']
    plans = db['subscription_plans']
    policies = db['platform_policies']
    role = ns['require_api_role']
    orgs = ns['organizations_collection']
    users = ns['users_collection']

    @app.on_event('startup')
    async def admin_indexes():
        plans.create_index('code', unique=True)
        plans.create_index('plan_id', unique=True)
        policies.create_index('kind', unique=True)

    def now():
        return datetime.now(timezone.utc)

    def safe(record):
        return {k: v for k, v in record.items() if k not in {'_id', 'password_hash', 'embedding'}}

    def listing(records, page, page_size, q, status, sort, direction, allowed):
        if sort not in allowed or direction not in {'asc', 'desc'} or status not in {'', 'active', 'inactive'}:
            raise HTTPException(400, 'Invalid listing options')
        needle = q.strip().casefold()
        records = [safe(r) for r in records if (not needle or any(needle in str(r.get(key, '')).casefold() for key in allowed))
                   and (not status or bool(r.get('is_active', True)) == (status == 'active'))]
        records.sort(key=lambda r: (r.get(sort) is not None, str(r.get(sort, '')).casefold())
                     if sort not in {'max_users', 'price_minor', 'users_count'} else (r.get(sort) is not None, r.get(sort, 0)),
                     reverse=direction == 'desc')
        page_size = min(100, max(1, page_size))
        page = min(max(1, page), max(1, (len(records) + page_size - 1) // page_size))
        paged = ns['paginate_items'](records, page, page_size)
        return {'items': paged['items'], 'pagination': paged['pagination']}

    @app.get('/api/org-admin/users')
    async def employee_list(request: Request, page: int = 1, page_size: int = 10, q: str = '', status: str = '', sort: str = 'created_at', direction: str = 'desc'):
        role(request, 'org_admin')
        records = list(users.find({'org_id': request.session['org_id']}, {'_id': 0, 'password_hash': 0}))
        for record in records:
            record['face_enrolled'] = ns['is_face_enrolled'](record['org_id'], record['employee_id'])
        return listing(records, page, page_size, q, status, sort, direction, {'employee_name', 'employee_id', 'email', 'created_at'})

    @app.put('/api/org-admin/users/{user_id}')
    async def employee_update(request: Request, user_id: str, payload: EmployeeUpdate):
        role(request, 'org_admin')
        scope = {'org_id': request.session['org_id'], 'user_id': user_id}
        employee = users.find_one(scope)
        if not employee:
            raise HTTPException(404, 'Employee not found')
        name, email = payload.employee_name.strip(), payload.email.strip().lower()
        if not name or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise HTTPException(400, 'Enter a name and a valid email address')
        if users.find_one({'email': email, 'user_id': {'$ne': user_id}}):
            raise HTTPException(409, 'User email already exists')
        update = {'employee_name': name, 'email': email}
        if payload.password:
            update['password_hash'] = ns['hash_password'](payload.password)
        try:
            users.update_one(scope, {'$set': update})
        except DuplicateKeyError:
            raise HTTPException(409, 'User email already exists')
        # Keep immutable employee IDs and all tracking/session references intact.
        for collection in (ns['collection'], ns['attendance_collection']):
            collection.update_many({'org_id': scope['org_id'], 'employee_id': employee['employee_id']}, {'$set': {'employee_name': name}})
        return {'success': True}

    @app.get('/api/superadmin/organizations')
    async def organization_list(request: Request, page: int = 1, page_size: int = 10, q: str = '', status: str = '', sort: str = 'created_at', direction: str = 'desc'):
        role(request, 'superadmin')
        records = ns['get_orgs_with_insights']()['all_orgs']
        return listing(records, page, page_size, q, status, sort, direction, {'org_name', 'org_code', 'admin_email', 'admin_name', 'created_at', 'users_count'})

    def policy_kind(kind):
        if kind not in {'terms', 'privacy'}:
            raise HTTPException(404, 'Policy not found')

    @app.get('/api/superadmin/policies/{kind}')
    async def policy_read(request: Request, kind: str):
        role(request, 'superadmin')
        policy_kind(kind)
        return safe(policies.find_one({'kind': kind}) or {'kind': kind, 'revision': 0, 'draft': '', 'published': None, 'history': []})

    @app.put('/api/superadmin/policies/{kind}')
    async def policy_save(request: Request, kind: str, payload: PolicyUpdate):
        role(request, 'superadmin')
        policy_kind(kind)
        if payload.publish and not payload.content.strip():
            raise HTTPException(400, 'Content is required to publish')
        scope = {'kind': kind}
        # Create revision zero once, then use compare-and-swap for every write.
        try:
            policies.update_one(scope, {'$setOnInsert': {'revision': 0, 'draft': '', 'published': None, 'history': []}}, upsert=True)
        except DuplicateKeyError:
            pass
        stamp = now()
        update = {'$set': {'draft': payload.content, 'updated_at': stamp}, '$inc': {'revision': 1}}
        if payload.publish:
            snapshot = {'content': payload.content, 'version': payload.revision + 1, 'published_at': stamp}
            update['$set']['published'] = snapshot
            update['$push'] = {'history': {'$each': [snapshot], '$slice': -20}}
        result = policies.find_one_and_update({**scope, 'revision': payload.revision}, update, return_document=ReturnDocument.AFTER)
        if not result:
            raise HTTPException(409, 'This policy changed. Reload before saving your changes.')
        return safe(result)

    @app.get('/api/org-admin/policies/{kind}', include_in_schema=False)
    @app.get('/api/policies/{kind}')
    async def published_policy(request: Request, kind: str):
        role(request, 'org_admin', 'user')
        policy_kind(kind)
        record = policies.find_one({'kind': kind})
        return {'kind': kind, 'published': record.get('published') if record else None}

    @app.get('/api/superadmin/plans')
    async def plan_list(request: Request, page: int = 1, page_size: int = 10, q: str = '', status: str = '', sort: str = 'created_at', direction: str = 'desc'):
        role(request, 'superadmin')
        return listing([plan_pricing(p) for p in plans.find({}, {'_id': 0})], page, page_size, q, status, sort, direction, {'name', 'code', 'description', 'created_at', 'price_minor', 'per_user_price_minor', 'max_users'})

    def plan_values(payload):
        values = payload.model_dump()
        values['name'] = values['name'].strip()
        if not values['name']:
            raise HTTPException(400, 'Plan name is required')
        return values

    @app.post('/api/superadmin/plans')
    async def plan_create(request: Request, payload: PlanInput):
        role(request, 'superadmin')
        record = {**plan_values(payload), 'plan_id': uuid.uuid4().hex, 'created_at': now(), 'updated_at': now()}
        try:
            plans.insert_one(record)
        except DuplicateKeyError:
            raise HTTPException(409, 'Plan code already exists')
        return safe(record)

    @app.put('/api/superadmin/plans/{plan_id}')
    async def plan_update(request: Request, plan_id: str, payload: PlanInput):
        role(request, 'superadmin')
        try:
            record = plans.find_one_and_update({'plan_id': plan_id}, {'$set': {**plan_values(payload), 'updated_at': now()}, '$unset': {'features': '', 'storage_gb': ''}}, return_document=ReturnDocument.AFTER)
        except DuplicateKeyError:
            raise HTTPException(409, 'Plan code already exists')
        if not record:
            raise HTTPException(404, 'Plan not found')
        return safe(record)

    @app.delete('/api/superadmin/plans/{plan_id}')
    async def plan_delete(request: Request, plan_id: str):
        role(request, 'superadmin')
        # Deactivation preserves assigned plans and historical subscription data.
        if orgs.find_one({'subscription.plan_id': plan_id}):
            raise HTTPException(409, 'This plan is assigned to an organization. Deactivate it instead.')
        # Require deactivation before deletion; assignments retain a plan snapshot.
        record = plans.find_one({'plan_id': plan_id})
        if not record:
            raise HTTPException(404, 'Plan not found')
        if record.get('is_active'):
            raise HTTPException(409, 'Deactivate the plan before deleting it')
        plans.delete_one({'plan_id': plan_id, 'is_active': False})
        return {'success': True}

    @app.put('/api/superadmin/orgs/{org_id}/subscription')
    async def assign_plan(request: Request, org_id: str, payload: AssignmentInput):
        role(request, 'superadmin')
        if not orgs.find_one({'org_id': org_id}):
            raise HTTPException(404, 'Organization not found')
        subscription = build_subscription(db, payload)
        orgs.update_one({'org_id': org_id}, {'$set': {'subscription': subscription}})
        return subscription

    @app.get('/api/org-admin/subscription')
    async def own_subscription(request: Request):
        role(request, 'org_admin')
        org = orgs.find_one({'org_id': request.session['org_id']})
        return {'org_name': org['org_name'], 'org_code': org['org_code'], 'is_active': org['is_active'],
                'users_count': ns['get_user_count'](org['org_id']), 'max_users': org.get('max_users', 0),
                'subscription': org.get('subscription')}
