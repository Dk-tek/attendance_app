# Frontend review and implementation checklist

## Architecture and scope

This repository was TrackPulse, not JesperChat, and is now branded Field Pixel. React 18, Vite 7, JavaScript,
Lucide icons and Leaflet use one shared stylesheet. App.jsx lazy-loads three
role panels and login. Navigation is local state under /app/; preserve these
entry points. api.js owns credentialed JSON requests. useLoad polls visible
pages every 30 seconds and discards obsolete responses.

FastAPI attendance.py owns signed cookie sessions, role checks, MongoDB,
attendance, face enrollment and the mobile API. mobile_api.py owns bearer
tokens, tracking and offline event deduplication. No chat, channels, sockets,
notifications, profile editing, help or about modules exist in this checkout.
Do not invent their figures or actions.

## Page review

| Page | Existing behavior | Improvement |
| --- | --- | --- |
| Login | Cookie authentication, theme, required fields | Retain flow, accessible feedback |
| Global overview | Actual organization/user/attendance totals | Compact shared header and cards |
| Organizations | Inline creation, row cards, detail/edit page | Table, modal forms, search/filter/sort, server pagination |
| Insights | All organizations, no pagination | Use paginated organization data |
| Org overview | Actual totals, mostly empty descriptive panel | Organization details and recent attendance |
| Employees | Inline creation squeezes table; toggle errors uncaught | Full-width listing, create/edit/view modals, confirmed status action |
| Attendance | Date/employee filters, grouped drilldown, lazy map | Preserve session trails, expose page size and record counts |
| Settings | Read-only Org Admin tracking settings | Preserve Super Admin ownership, compact layout |
| User overview/records/map | Real summary, date filters and paginated records | Shared design and pagination, preserve maps |

## Backend gaps and decisions

Existing JSON APIs support organization create/update/toggle, employee create/
toggle, attendance and dashboards. Legacy employee edit is a multipart redirect
flow and cannot reliably report JSON success/errors. Add a scoped JSON employee
update using immutable employee IDs to preserve attendance/session identity.
Deletion is not supported for user accounts or organizations; the face-profile
DELETE route is not account deletion and must not be repurposed.

New additive admin_modules.py routes provide policies, subscription plans and
plan assignment using existing session authorization. Organization creation,
plan CRUD, policy creation and policy publishing remain Super Admin operations.
Org Admin can inspect its organization/subscription. Org Admin and employees
can read the same published platform terms and privacy policy; drafts and
history are available only to Super Admin. Legacy tenant documents are retained
unchanged, pending explicit review before platform-wide publication.

Policies store text with basic Markdown formatting, draft and published content,
revision checks and immutable publish snapshots. Rendering creates React nodes,
never raw HTML. No rich-text library existed to reuse. Plans use integer minor
currency units and explicit currency. The current pricing model is base price
plus per-user price times registered employees, including inactive accounts;
features and storage fields were removed at the user's request. Assignments
do not change the existing employee quota implicitly.
No payment gateway is introduced.

## Sequence and validation

1. Shared responsive shell, feedback, dialog and listing controls; build.
2. Employee listing and forms; scoped backend regression tests and build.
3. Organization listing, modal editing and insights; build.
4. Policy drafts/publishing, plans and assignment; API role/isolation tests.
5. Full frontend build, frontend tests and Python regression suite.

Use additive APIs and preserve all existing response keys. Search/filter/sort
must run before pagination on the server. Existing dashboard APIs still return
all_users/all_orgs for compatibility; new listings should not depend on them.
Browser verification and live database verification must be reported separately
from automated tests. Never read or print .env secrets during this work.

## Completed verification

- Shared layout and modal/listing controls implemented and built.
- Employee view/create/edit and confirmed activation/deactivation implemented.
- Organization table, modal create/edit, subscription assignment and paginated
  insights implemented under Super Admin.
- Platform terms/privacy draft, preview, publish and history implemented under
  Super Admin; Org Admin and employee navigation expose only published documents.
- Plan view/create/edit, activation/deactivation and permitted deletion implemented.
- Attendance and user record pagination now expose configurable page sizes.
- Production build passed; 4 frontend map/SEO tests and 31 Python tests passed.
- Isolated Edge browser checks passed: employee create/edit/status, search and
  pagination, dirty-form cancellation, policy save/publish and safe rendering,
  employee read-only published content, plan creation/assignment, organization
  edit, light/dark themes and tablet/mobile page overflow.
- Browser screenshots are in ignored `.browser-artifacts/` for local review.

No production database, live face inference, or deployed site was tested or
modified. Existing mobile regression tests pass against isolated test data.
Backend and rebuilt frontend must be deployed together, then the backend
restarted to register additive APIs and new indexes. Test tooling emitted
framework deprecation warnings for the existing startup/shutdown hook style.
