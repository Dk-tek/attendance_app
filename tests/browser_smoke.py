"""Opt-in browser integration checks against an isolated in-memory test server.

Run after npm run build. Uses installed Playwright and Edge; never reads .env
or connects to the production database. Screenshots go to .browser-artifacts.
"""
import ast
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mongomock
import pymongo
import uvicorn
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright


def run():
    previous = Path.cwd()
    with tempfile.TemporaryDirectory() as isolated:
        os.chdir(isolated)
        os.environ['SESSION_SECRET'] = 'browser-fixture-session-secret-at-least-32-chars'
        os.environ['COOKIE_SECURE'] = 'false'
        os.environ['SUPERADMIN_EMAIL'] = 'super@example.test'
        os.environ['SUPERADMIN_PASSWORD'] = 'test-password'
        pymongo.MongoClient = lambda *a, **kw: mongomock.MongoClient()
        source = ROOT / 'attendance.py'
        tree = ast.parse(source.read_text())
        heavy = {'cv2', 'mediapipe', 'numpy', 'onnxruntime', 'PIL', 'sklearn'}
        tree.body = [node for node in tree.body if not (
            isinstance(node, ast.Import) and any(a.name.split('.')[0] in heavy for a in node.names)
            or isinstance(node, ast.ImportFrom) and (node.module or '').split('.')[0] in heavy)]
        ns = {'np': SimpleNamespace(array=lambda *a, **kw: None, float32=None), 'mp': SimpleNamespace(solutions=SimpleNamespace(face_mesh=None))}
        exec(compile(tree, str(source), 'exec'), ns)
        ns['app'].mount('/app', StaticFiles(directory=str(ROOT / 'frontend' / 'dist'), html=True))
        ns['organizations_collection'].insert_one({'org_id': 'browser-org', 'org_name': 'Browser Test Organization', 'org_code': 'browser-test', 'max_users': 100, 'is_active': True})
        ns['admin_users_collection'].insert_one({'org_id': 'browser-org', 'name': 'Test Admin', 'email': 'admin@example.test', 'password_hash': ns['hash_password']('test-password'), 'is_active': True})
        for i in range(23):
            ns['users_collection'].insert_one({'org_id': 'browser-org', 'user_id': f'user-{i}', 'employee_id': f'EMP{i:03}', 'employee_name': f'Employee {i:02}', 'email': f'employee{i}@example.test', 'password_hash': ns['hash_password']('test-password'), 'is_active': True})
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(ns['app'], host='127.0.0.1', port=port, log_level='error'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(100):
            if server.started:
                break
            time.sleep(.1)
        assert server.started, 'Test server failed to start'
        output = ROOT / '.browser-artifacts'
        output.mkdir(exist_ok=True)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='msedge', headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{port}/app/')
                page.get_by_role('heading', name='Every check-in. Every move. In focus.').wait_for()
                assert page.title().startswith('Field Pixel')
                assert page.locator('link[rel="canonical"]').get_attribute('href') == 'https://attendance.dreamcapture.in/app/'
                assert page.locator('meta[name="robots"]').get_attribute('content') == 'index,follow'
                page.screenshot(path=str(output / 'field-pixel-home-desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Product page overflows on mobile'
                page.screenshot(path=str(output / 'field-pixel-home-mobile.png'), full_page=True)
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.get_by_role('button', name='Open sign in', exact=True).click()
                page.wait_for_function('document.title === "Sign In | Field Pixel"')
                assert 'noindex' in page.locator('meta[name="robots"]').get_attribute('content')
                page.get_by_label('Email or employee ID').fill('admin@example.test')
                page.get_by_label('Password', exact=True).fill('test-password')
                page.get_by_role('button', name='Sign in', exact=True).click()
                page.get_by_role('navigation').get_by_role('button', name='Users', exact=True).click()
                page.get_by_text('1–10 of 23 records').wait_for()
                page.get_by_role('button', name='Page 2', exact=True).click()
                page.get_by_text('11–20 of 23 records').wait_for()
                page.get_by_label('Search records').fill('Employee 01')
                page.get_by_text('1–1 of 1 records').wait_for()
                page.get_by_role('button', name='Edit', exact=True).click()
                page.get_by_label('Full name', exact=True).fill('Updated Browser Employee')
                page.get_by_role('button', name='Save changes', exact=True).click()
                page.get_by_text('Employee updated.', exact=True).wait_for()
                page.get_by_label('Search records').fill('')
                page.get_by_text('1–10 of 23 records').wait_for()
                page.get_by_role('button', name='Create employee', exact=True).click()
                page.get_by_label('Full name', exact=True).fill('Unsaved')
                page.get_by_role('button', name='Cancel', exact=True).click()
                page.get_by_text('Discard unsaved changes?', exact=True).wait_for()
                page.get_by_role('button', name='Discard changes', exact=True).click()
                page.get_by_role('button', name='Create employee', exact=True).click()
                page.get_by_label('Employee ID', exact=True).fill('NEW001')
                page.get_by_label('Full name', exact=True).fill('Created Browser Employee')
                page.get_by_label('Email address', exact=True).fill('created@example.test')
                page.get_by_label('Password', exact=True).fill('test-password')
                page.get_by_role('dialog').get_by_role('button', name='Create employee', exact=True).click()
                page.get_by_text('1–10 of 24 records').wait_for()
                page.get_by_label('Search records').fill('Created Browser Employee')
                page.get_by_text('1–1 of 1 records').wait_for()
                page.get_by_role('button', name='Deactivate', exact=True).click()
                page.get_by_role('button', name='Confirm', exact=True).click()
                page.get_by_text('Employee status updated.', exact=True).wait_for()
                page.get_by_label('Search records').fill('')
                page.get_by_text('1–10 of 24 records').wait_for()
                page.screenshot(path=str(output / 'employees-desktop.png'), full_page=True)
                page.get_by_role('button', name='Toggle theme', exact=True).click()
                assert page.locator('html').get_attribute('data-theme') == 'dark'
                page.screenshot(path=str(output / 'employees-dark.png'), full_page=True)
                page.get_by_role('button', name='Toggle theme', exact=True).click()
                page.set_viewport_size({'width': 900, 'height': 1000})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Tablet page overflows'
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.get_by_role('navigation').get_by_role('button', name='Terms & Conditions', exact=True).click()
                page.get_by_text('No published content', exact=True).wait_for()
                assert page.get_by_role('button', name='Create policy', exact=True).count() == 0
                page.wait_for_function('document.title === "Terms & Conditions | Org Admin | Field Pixel"')
                page.get_by_role('navigation').get_by_role('button', name='Users', exact=True).click()
                page.get_by_text('1–10 of 24 records').wait_for()
                page.set_viewport_size({'width': 390, 'height': 844})
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile page overflows'
                page.get_by_role('button', name='Create employee', exact=True).click()
                assert page.get_by_role('dialog').bounding_box()['width'] <= 390
                page.screenshot(path=str(output / 'employee-mobile.png'), full_page=True)
                page.get_by_role('button', name='Close dialog').click()
                page.get_by_role('button', name='Logout', exact=True).click()
                page.get_by_role('button', name='Open sign in', exact=True).click()
                page.get_by_label('Email or employee ID').fill('super@example.test')
                page.get_by_label('Password', exact=True).fill('test-password')
                page.get_by_role('button', name='Sign in', exact=True).click()
                page.set_viewport_size({'width': 1440, 'height': 1000})
                for label, heading in [('Terms & Conditions', 'Test Terms'), ('Privacy Policy', 'Test Privacy')]:
                    page.get_by_role('navigation').get_by_role('button', name=label, exact=True).click()
                    page.get_by_role('button', name='Create policy', exact=True).click()
                    page.get_by_label('Policy content', exact=True).fill(f'# {heading}\n**Safe policy**\n- First item\n<script>alert(1)</script>')
                    page.get_by_role('button', name='Save draft', exact=True).click()
                    page.get_by_text('Draft saved.', exact=True).wait_for()
                    page.get_by_role('button', name='Edit policy', exact=True).click()
                    page.get_by_role('button', name='Publish policy', exact=True).click()
                    page.get_by_text('Policy published.', exact=True).wait_for()
                    page.get_by_text(heading, exact=True).wait_for()
                    assert page.locator('.policyContent script').count() == 0
                page.screenshot(path=str(output / 'superadmin-policy-desktop.png'), full_page=True)
                page.get_by_role('navigation').get_by_role('button', name='Subscription plans', exact=True).click()
                page.get_by_role('button', name='Create plan', exact=True).click()
                page.get_by_label('Plan name', exact=True).fill('Browser Test Plan')
                page.get_by_label('Plan code', exact=True).fill('browser-plan')
                page.get_by_label('Base price', exact=True).fill('99.50')
                page.get_by_label('Price per user', exact=True).fill('12.50')
                assert page.get_by_label('Storage allocation (GB)', exact=True).count() == 0
                assert page.get_by_text('Features (one per line, up to 50)', exact=True).count() == 0
                page.get_by_text('₹224.50', exact=True).wait_for()
                page.get_by_role('button', name='Save plan', exact=True).click()
                page.get_by_text('Plan saved.', exact=True).wait_for()
                page.get_by_role('navigation').get_by_role('button', name='Organizations', exact=True).click()
                page.get_by_role('button', name='Assign plan', exact=True).click()
                page.get_by_role('radio').first.check()
                page.get_by_label('Base price', exact=True).fill('100')
                page.get_by_role('dialog').get_by_role('button', name='Save subscription', exact=True).click()
                page.get_by_text('Subscription assigned.', exact=True).wait_for()
                page.get_by_role('button', name='View / Edit', exact=True).click()
                page.get_by_role('button', name='Edit organization', exact=True).click()
                page.get_by_label('Organization name', exact=True).fill('Updated Organization')
                page.get_by_label('Change subscription and pricing', exact=True).check()
                page.get_by_label('Price per user', exact=True).fill('10')
                page.get_by_role('button', name='Save changes', exact=True).click()
                page.get_by_text('Organization updated.', exact=True).wait_for()
                page.screenshot(path=str(output / 'organization-desktop.png'), full_page=True)
                page.get_by_role('button', name='Collapse navigation', exact=True).click()
                page.get_by_role('button', name='Expand navigation', exact=True).click()
                page.get_by_role('button', name='Logout', exact=True).click()
                page.get_by_role('button', name='Open sign in', exact=True).click()
                page.get_by_label('Email or employee ID').fill('admin@example.test')
                page.get_by_label('Password', exact=True).fill('test-password')
                page.get_by_role('button', name='Sign in', exact=True).click()
                for label, heading in [('Terms & Conditions', 'Test Terms'), ('Privacy Policy', 'Test Privacy')]:
                    page.get_by_role('navigation').get_by_role('button', name=label, exact=True).click()
                    page.get_by_text(heading, exact=True).wait_for()
                    assert page.get_by_role('button', name='Edit policy', exact=True).count() == 0
                page.get_by_role('button', name='Logout', exact=True).click()
                page.get_by_role('button', name='Open sign in', exact=True).click()
                page.get_by_label('Email or employee ID').fill('employee0@example.test')
                page.get_by_label('Password', exact=True).fill('test-password')
                page.get_by_role('button', name='Sign in', exact=True).click()
                page.get_by_role('navigation').get_by_role('button', name='Terms & Conditions', exact=True).click()
                page.get_by_text('Test Terms', exact=True).wait_for()
                assert page.get_by_role('button', name='Edit policy', exact=True).count() == 0
                page.wait_for_function('document.title === "Terms & Conditions | Employee | Field Pixel"')
                assert 'noindex' in page.locator('meta[name="robots"]').get_attribute('content')
                assert not errors, errors
                browser.close()
                print('Browser checks passed: Field Pixel product page and profile sign-in, desktop/mobile layouts, employee CRUD/status, policy publishing, base/per-user pricing totals, plan assignment, existing organization price editing and icon navigation collapse.')
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            os.chdir(previous)


if __name__ == '__main__':
    run()
