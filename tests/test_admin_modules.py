"""Regression checks use the actual FastAPI router and isolated MongoDB fake."""
import pytest
from test_mobile_routes import server


def admin_login(client, ns):
    ns['organizations_collection'].update_one({'org_id': 'org'}, {'$set': {'org_name': 'Example', 'max_users': 10}})
    ns['admin_users_collection'].insert_one({'org_id': 'org', 'name': 'Admin', 'email': 'admin@example.com', 'password_hash': ns['hash_password']('password'), 'is_active': True})
    assert client.post('/api/auth/login', json={'username': 'admin@example.com', 'password': 'password', 'role': 'org_admin'}).status_code == 200


def super_login(client, ns):
    ns['SUPERADMIN_PASSWORD'] = 'test-super-password'
    assert client.post('/api/auth/login', json={'username': ns['SUPERADMIN_EMAIL'], 'password': 'test-super-password', 'role': 'superadmin'}).status_code == 200


def test_employee_listing_search_pagination_and_safe_update(server):
    client, ns = server
    admin_login(client, ns)
    ns['users_collection'].update_one({'employee_id': 'employee'}, {'$set': {'user_id': 'mine'}})
    ns['users_collection'].insert_one({'user_id': 'other', 'org_id': 'other-org', 'employee_id': 'private', 'employee_name': 'Private', 'email': 'private@example.com'})
    response = client.get('/api/org-admin/users?q=employee&sort=email&page_size=1').json()
    assert response['pagination']['total'] == 1
    assert 'password_hash' not in response['items'][0]
    assert client.get('/api/org-admin/users?status=inactive').json()['pagination']['total'] == 0
    assert client.get('/api/org-admin/users?sort=password_hash').status_code == 400
    payload = {'employee_name': 'Updated', 'email': 'updated@example.com'}
    assert client.put('/api/org-admin/users/other', json=payload).status_code == 404
    assert client.put('/api/org-admin/users/mine', json=payload).status_code == 200
    user = ns['users_collection'].find_one({'user_id': 'mine'})
    assert user['employee_id'] == 'employee'
    assert user['employee_name'] == 'Updated'
    assert ns['verify_password']('password', user['password_hash'])


def test_monitoring_search_range_complete_timeline_and_tenant_isolation(server):
    client, ns = server
    admin_login(client, ns)
    for org, employee in [('org', 'employee'), ('other-org', 'private')]:
        for hour in range(1, 5):
            ns['attendance_collection'].insert_one({'org_id': org, 'employee_id': employee, 'employee_name': 'Employee', 'attendance_type': 'check_in', 'timestamp': f'2026-11-10T0{hour}:00:00+00:00'})
        ns['location_collection'].insert_one({'org_id': org, 'employee_id': employee, 'timestamp': '2026-11-10T05:00:00+00:00', 'tracking_status': 'failed', 'remark': 'No GPS fix'})
    for search in ['EMPLOYEE', 'employee@example.com']:
        response = client.get('/api/org-admin/attendance', params={'q': search, 'start': '2026-11-10', 'end': '2026-11-10', 'page_size': 1, 'include_timeline': True})
        assert response.status_code == 200
        result = response.json()
        assert len(result['rows']) == 1
        assert len(result['timeline']) == 5
        assert {event['employee_id'] for event in result['timeline']} == {'employee'}
        assert result['timeline'][-1]['tracking_status'] == 'failed'
        assert result['groups_pagination']['total'] == 1
    assert client.get('/api/org-admin/attendance?q=private').json()['groups'] == []
    assert client.get('/api/org-admin/attendance?start=2026-11-11').json()['groups'] == []
    assert client.get('/api/org-admin/attendance?start=2026-11-12&end=2026-11-10').status_code == 400
    assert client.get('/api/org-admin/attendance?start=bad').status_code == 400
    assert 'timeline' not in client.get('/api/org-admin/attendance').json()
    client.post('/api/auth/logout')
    assert client.get('/api/org-admin/attendance?include_timeline=true').status_code == 401


@pytest.mark.parametrize('kind', ['terms', 'privacy'])
def test_superadmin_policy_publish_conflict_and_readonly_roles(server, kind):
    client, ns = server
    admin_login(client, ns)
    endpoint = '/api/superadmin/policies/' + kind
    draft = {'content': '# Terms\nPrivate draft', 'revision': 0, 'publish': False}
    assert client.get(endpoint).status_code == 401
    assert client.put(endpoint, json=draft).status_code == 401
    assert client.put('/api/org-admin/policies/' + kind, json=draft).status_code == 405
    # Existing tenant policies must not become the platform's policy by accident.
    ns['db']['organization_policies'].insert_one({'org_id': 'org', 'kind': kind, 'published': {'content': 'Old tenant text'}})
    super_login(client, ns)
    assert client.get(endpoint).json()['revision'] == 0
    assert client.put(endpoint, json=draft).status_code == 200
    assert client.put(endpoint, json=draft).status_code == 409
    assert client.post('/api/auth/login', json={'username': 'admin@example.com', 'password': 'password', 'role': 'org_admin'}).status_code == 200
    assert client.get('/api/policies/' + kind).json()['published'] is None
    assert 'draft' not in client.get('/api/org-admin/policies/' + kind).json()
    super_login(client, ns)
    draft.update(revision=1, publish=True)
    assert client.put(endpoint, json=draft).json()['published']['version'] == 2
    assert client.post('/api/auth/login', json={'username': 'employee@example.com', 'password': 'password', 'role': 'user'}).status_code == 200
    assert client.get(endpoint).status_code == 401
    assert client.put(endpoint, json=draft).status_code == 401
    published = client.get('/api/policies/' + kind).json()
    assert 'history' not in published and 'draft' not in published
    assert published['published']['content'] == draft['content']
    ns['organizations_collection'].insert_one({'org_id': 'tenant-two', 'org_name': 'Other tenant', 'org_code': 'other', 'is_active': True})
    ns['admin_users_collection'].insert_one({'org_id': 'tenant-two', 'name': 'Other Admin', 'email': 'other@example.com', 'password_hash': ns['hash_password']('password'), 'is_active': True})
    assert client.post('/api/auth/login', json={'username': 'other@example.com', 'password': 'password', 'role': 'org_admin'}).status_code == 200
    assert client.get('/api/policies/' + kind).json()['published']['content'] == draft['content']
    assert client.put(endpoint, json=draft).status_code == 401


def test_seo_discovery_only_includes_public_product_page(server):
    from xml.etree import ElementTree
    client, _ = server
    robots = client.get('/robots.txt')
    assert robots.status_code == 200
    assert 'Sitemap: https://attendance.dreamcapture.in/sitemap.xml' in robots.text
    assert 'Disallow: /api/' in robots.text
    sitemap = client.get('/sitemap.xml')
    assert sitemap.status_code == 200
    root = ElementTree.fromstring(sitemap.text)
    assert [e.text for e in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')] == ['https://attendance.dreamcapture.in/app/']


def test_employee_filters_and_sort_apply_before_pagination(server):
    client, ns = server
    admin_login(client, ns)
    for i in range(25):
        ns['users_collection'].insert_one({'user_id': f'row-{i}', 'org_id': 'org', 'employee_id': f'ID{i:02}', 'employee_name': f'Name {i:02}', 'email': f'{i}@example.com', 'is_active': i % 2 == 0})
    first = client.get('/api/org-admin/users?q=Name&status=active&sort=employee_name&direction=desc&page_size=10').json()
    assert first['pagination']['total'] == 13
    assert len(first['items']) == 10
    assert first['items'][0]['employee_name'] == 'Name 24'
    second = client.get('/api/org-admin/users?q=Name&status=active&sort=employee_name&direction=desc&page_size=10&page=2').json()
    assert len(second['items']) == 3
    assert second['items'][-1]['employee_name'] == 'Name 00'


PLAN = {'name': 'Team', 'code': 'team', 'price_minor': 9900, 'per_user_price_minor': 1500, 'currency': 'INR', 'billing_cycle': 'monthly', 'max_users': 25, 'is_active': True}


def test_plans_roles_validation_and_assignment(server):
    client, ns = server
    admin_login(client, ns)
    assert client.post('/api/superadmin/plans', json=PLAN).status_code == 401
    super_login(client, ns)
    response = client.post('/api/superadmin/plans', json=PLAN)
    assert response.status_code == 200
    plan_id = response.json()['plan_id']
    assert client.post('/api/superadmin/plans', json=PLAN).status_code == 409
    assert client.post('/api/superadmin/plans', json={**PLAN, 'price_minor': -1}).status_code == 422
    assert client.get('/api/superadmin/plans?q=Team').json()['pagination']['total'] == 1
    assignment = {'plan_id': plan_id, 'starts_at': '2026-01-01T00:00:00Z', 'ends_at': '2027-01-01T00:00:00Z'}
    assert client.put('/api/superadmin/orgs/org/subscription', json={**assignment, 'ends_at': '2025-01-01T00:00:00Z'}).status_code == 400
    assert client.put('/api/superadmin/orgs/org/subscription', json=assignment).status_code == 200
    assert ns['organizations_collection'].find_one({'org_id': 'org'})['max_users'] == 10
    assert client.delete('/api/superadmin/plans/' + plan_id).status_code == 409
    assert client.put('/api/superadmin/plans/' + plan_id, json={**PLAN, 'is_active': False}).status_code == 200
    assert client.put('/api/superadmin/orgs/org/subscription', json=assignment).status_code == 400
    ns['organizations_collection'].update_one({'org_id': 'org'}, {'$unset': {'subscription': ''}})
    assert client.delete('/api/superadmin/plans/' + plan_id).status_code == 200


@pytest.mark.parametrize('path', ['/api/org-admin/users', '/api/org-admin/policies/terms', '/api/superadmin/plans', '/api/superadmin/organizations', '/api/org-admin/subscription', '/api/policies/privacy'])
def test_new_endpoints_require_session(server, path):
    client, _ = server
    assert client.get(path).status_code == 401


def test_plan_pricing_without_features_or_storage_and_legacy_defaults(server):
    client, ns = server
    super_login(client, ns)
    response = client.post('/api/superadmin/plans', json=PLAN)
    assert response.status_code == 200
    assert response.json()['per_user_price_minor'] == 1500
    assert 'storage_gb' not in response.json() and 'features' not in response.json()
    assert client.post('/api/superadmin/plans', json={**PLAN, 'code': 'negative', 'per_user_price_minor': -1}).status_code == 422
    ns['db']['subscription_plans'].insert_one({'plan_id': 'legacy', 'name': 'Legacy', 'code': 'legacy', 'price_minor': 3000, 'currency': 'INR', 'billing_cycle': 'monthly', 'max_users': 10, 'features': [], 'storage_gb': 5, 'is_active': True})
    legacy = client.get('/api/superadmin/plans?q=Legacy').json()['items'][0]
    assert legacy['per_user_price_minor'] == 0
    assert 'storage_gb' not in legacy and 'features' not in legacy


def test_organization_create_and_edit_can_set_pricing_without_changing_other_orgs(server):
    client, ns = server
    admin_login(client, ns)
    super_login(client, ns)
    plan = client.post('/api/superadmin/plans', json=PLAN).json()
    assignment = {'plan_id': plan['plan_id'], 'starts_at': '2026-01-01T00:00:00Z', 'price_minor': 5000, 'per_user_price_minor': 1200}
    payload = {'org_name': 'New customer', 'org_code': 'new-customer', 'max_users': 20, 'admin_name': 'Customer admin', 'admin_email': 'new@example.com', 'admin_password': 'password', 'subscription': assignment}
    invalid = client.post('/api/superadmin/orgs', json={**payload, 'subscription': {**assignment, 'plan_id': 'missing'}})
    assert invalid.status_code == 400
    assert ns['organizations_collection'].count_documents({'org_code': 'new-customer'}) == 0
    response = client.post('/api/superadmin/orgs', json=payload)
    assert response.status_code == 200
    created = ns['organizations_collection'].find_one({'org_id': response.json()['org_id']})
    assert created['subscription']['plan']['price_minor'] == 5000
    assert created['subscription']['plan']['per_user_price_minor'] == 1200
    # Existing tenant changes go through its standard edit form and endpoint.
    update = {**payload, 'org_name': 'Example', 'org_code': 'ORG', 'admin_name': 'Admin', 'admin_email': 'admin@example.com'}
    assert client.put('/api/superadmin/orgs/org', json=update).status_code == 200
    current = ns['organizations_collection'].find_one({'org_id': 'org'})
    assert current['subscription']['plan']['price_minor'] == 5000
    assert ns['db']['subscription_plans'].find_one({'plan_id': plan['plan_id']})['price_minor'] == 9900
    assert client.post('/api/auth/login', json={'username': 'admin@example.com', 'password': 'password', 'role': 'org_admin'}).status_code == 200
    own = client.get('/api/org-admin/subscription').json()
    assert own['users_count'] == 1
    assert own['subscription']['plan']['per_user_price_minor'] == 1200
    assert client.put('/api/superadmin/orgs/org/subscription', json=assignment).status_code == 401
