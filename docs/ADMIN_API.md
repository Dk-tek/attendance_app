# Additive admin API contracts

All endpoints use the existing signed session cookie, `credentials: include`,
and `require_api_role`. No bearer-token, login, face recognition or tracking
contracts are changed. Deploy `admin_modules.py` together with `attendance.py`
and the rebuilt `frontend/dist`; restart the backend to register the routes
and create the new indexes. No new production dependency is needed.

## Listings

`GET /api/org-admin/users`: own tenant only.
`GET /api/superadmin/organizations`: Super Admin only.
`GET /api/superadmin/plans`: Super Admin only.

Common query: `page=1&page_size=10&q=&status=&sort=created_at&direction=desc`.
Sizes are clamped to 1–100; out-of-range pages clamp to the final page. Status
is empty, `active`, or `inactive`. Search is literal, case insensitive, and
applies before sorting and pagination. Responses:

```json
{"items": [], "pagination": {"page": 1, "page_size": 10, "total": 0,
"pages": 1, "has_next": false, "has_prev": false}}
```

Users: `employee_id`, `employee_name`, `email`, `created_at` sort keys.
Organizations: `org_name`, `org_code`, `admin_name`, `admin_email`,
`users_count`, `created_at`. Plans: `name`, `code`, `description`,
`price_minor`, `per_user_price_minor`, `max_users`, `created_at`. Invalid options return 400.
Password hashes and face embeddings are excluded.

These endpoints paginate on the server but currently aggregate/filter in
memory, matching the existing dashboard architecture. For larger deployments,
move queries and counts into MongoDB aggregation before scaling record volume.
Legacy dashboard `all_users` and `all_orgs` keys remain for compatibility.

## Employee edit

`PUT /api/org-admin/users/{user_id}` with
`{"employee_name":"Name","email":"name@example.com","password":""}`.
Empty password preserves the hash. Employee ID cannot change through this API.
Cross-tenant IDs return 404; duplicate emails return 409. Response:
`{"success":true}`. Existing create and status-toggle APIs are reused.

Account/organization deletion is deliberately unavailable: no safe existing
account deletion contract exists. The existing face DELETE endpoint removes
face enrollment only and is not an account deletion endpoint.

## Policies

Super Admin only: `GET /api/superadmin/policies/{terms|privacy}` returns the platform's
`kind`, `revision`, `draft`, `published`, `history`, and timestamps.
Missing content returns revision zero, empty draft and null published.

Super Admin only: `PUT` the same path with
`{"content":"# Heading\nPolicy text","revision":0,"publish":false}`.
Content is at most 100,000 characters. Every save increments revision; stale
revisions return 409 without overwriting another editor's content. Publishing
requires nonblank content and stores a snapshot:
`{"content":"...","version":1,"published_at":"ISO datetime"}`.
The latest 20 publication snapshots are retained, keeping worst-case Unicode
content below MongoDB's per-document size limit. Saving a draft preserves the
published version. Response is the complete updated policy record.

`GET /api/policies/{terms|privacy}` lets authenticated employees and Org Admin
read the same platform-wide published snapshot. It never returns drafts or
history, and is not accessible without a session. The legacy Org Admin GET
path is a read-only alias; its PUT route no longer exists. Org Admin and
employee attempts to use Super Admin management APIs fail authorization.

Platform documents use the new `platform_policies` collection, unique by kind.
Previously saved tenant policies in `organization_policies` are retained
unchanged but are not automatically promoted to platform policy. A Super Admin
must review and publish the platform-wide terms and privacy content.

The editor supports headings, paragraphs, lists, bold, italic and HTTPS/HTTP
links as basic Markdown. React renders text and safe formatting nodes; raw HTML
is never inserted into the DOM.

## Plans

Super Admin: `POST /api/superadmin/plans`,
`PUT /api/superadmin/plans/{plan_id}`:

```json
{"name":"Team","code":"team","description":"Team allocation",
"price_minor":9900,"per_user_price_minor":1500,"currency":"INR",
"billing_cycle":"monthly","max_users":25,"is_active":true}
```

Price uses integer hundredths for the supported INR/USD/EUR/GBP currencies.
`price_minor` is the base charge; `per_user_price_minor` is the charge per
registered employee. Both are nonnegative integers. The UI shows
base + per-user charge × registered employees, including inactive employees.
Plan listings also show an estimate at the plan's user limit.
Billing cycle is monthly/yearly; user limit >= 1. Features and storage have
been removed. Legacy flat-price plans default to zero per-user charge and
remain usable without a database migration.
Codes contain 2–40 lowercase letters, digits, underscores or hyphens. Responses
include the saved plan, `plan_id`, `created_at`, and `updated_at`.
Duplicate codes return 409. Updating `is_active` activates/deactivates.

`DELETE /api/superadmin/plans/{plan_id}` returns success only for inactive,
unassigned plans. Assigned or active plans return 409. There is no payment,
automatic billing, storage metering or entitlement enforcement integration.

## Assignment and usage

Super Admin: `PUT /api/superadmin/orgs/{org_id}/subscription`:

```json
{"plan_id":"id","starts_at":"2026-11-08T00:00:00+05:30",
"ends_at":"2027-11-08T23:59:59+05:30",
"price_minor":5000,"per_user_price_minor":1200}
```

End may be null, otherwise it must follow start. Only active plans can be
assigned. Response contains the assignment with a complete plan snapshot.
Base and per-user overrides are optional; omitted overrides use the plan's
defaults. Overrides affect this organization only.
Plan changes do not retroactively alter agreed assignments. Assignment does
not alter existing `max_users` business rules; Super Admin edits that limit
through the existing organization API. This preserves production quotas.

Org Admin: `GET /api/org-admin/subscription` returns own org name/code/status,
`users_count`, `max_users`, and optional `subscription`. Dates determine display
status (scheduled/active/expired); expiry does not automatically revoke access.

The existing organization create/update JSON APIs also accept an optional
`subscription` object using the same assignment schema. Leaving it absent
preserves existing behavior and pricing. Invalid subscriptions are rejected
before organization/admin writes. Existing organizations can change pricing
from their edit modal or the subscription pricing action.

## Public product page

The `/app/` entry now shows the Field Pixel product page. Its profile icon and
workspace buttons open `#login` for visitors or `#workspace` for authenticated
users. Login remains the existing cookie flow; logout returns to the product
page. The provided logo is served locally. Product visuals are labeled
illustrations; attendance and admin figures still use backend data.

## SEO and indexing

Production origin: `https://attendance.dreamcapture.in`. The public landing
page canonical is `/app/`, matching the root redirect. Its initial HTML includes
a title, description, canonical, Open Graph and Twitter metadata, and truthful
SoftwareApplication JSON-LD. No invented reviews, ratings or free offers are used.

Every workspace page and login have distinct titles and descriptions updated
on navigation. Authenticated pages and login use `noindex,nofollow,noarchive`;
canonical and public-product structured data are removed while in private views.
Private policy documents remain authenticated and are not added to the sitemap.

`GET /robots.txt` points to `https://attendance.dreamcapture.in/sitemap.xml`
and disallows API/legacy admin routes. `GET /sitemap.xml` lists only the public
product URL. Both are served by FastAPI at the domain root, with one-hour public
cache headers. The application remains client rendered; metadata does not turn
private role pages into public search landing pages.

## Verification

`npm run build` and `npm test` in frontend; `python -m pytest tests -q` with
requirements-test.txt installed. `python tests/browser_smoke.py` additionally
uses installed Playwright, Uvicorn and Edge. It runs against a temporary mock
database, never .env or production, and captures screenshots locally.
