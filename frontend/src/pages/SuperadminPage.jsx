import { useState } from "react";
import { Building2, CalendarDays, ShieldCheck, Users } from "lucide-react";
import { api } from "../api";
import { DataTable } from "../components/DataTable";
import { Loading, Notice } from "../components/Feedback";
import { PaginationControls } from "../components/PaginationControls";
import { Stat } from "../components/Stat";
import { useLoad } from "../hooks/useLoad";
import { Badge, dateLabel, ListingTools, initialQuery } from "../components/Listing";
import { Modal, ConfirmAction } from "../components/Modal";
import { PlansPage, AssignmentModal } from "./PlansPage";
import { subscriptionStatus } from "./SubscriptionPage";
import { money, totalMinor, pricingForm, pricingPayload, PricingFields } from "../components/Pricing";
import { PlanPicker, assignmentPayload, localDate } from "../components/PlanPicker";
import { PolicyPage } from "./PolicyPage";

export function SuperadminPage({ activePage, setActivePage }) {
  if (["terms", "privacy"].includes(activePage)) return <PolicyPage key={activePage} kind={activePage} editable />;
  if (activePage === "plans") return <PlansPage />;
  if (activePage === "organizations" || activePage === "insights") return <OrganizationsPage key={activePage} insights={activePage === "insights"} />;
  return <SuperOverview setActivePage={setActivePage} />;
}

function SuperOverview({ setActivePage }) {
  const { data, loading, error } = useLoad(() => api.superadminDashboard({ page_size: 10 }), []);
  if (loading) return <Loading />;
  if (error) return <Notice text={error} />;
  return <div className="stack"><section className="statsGrid">
    <Stat label="Organizations" value={data.summary.organizations} detail={`${data.summary.active_organizations} active`} icon={Building2} />
    <Stat label="Employees" value={data.summary.users} detail="Across all organizations" icon={Users} />
    <Stat label="Face profiles" value={data.summary.face_profiles} detail="Ready for authentication" icon={ShieldCheck} />
    <Stat label="Today records" value={data.summary.attendance_today} detail="Check-in and check-out events" icon={CalendarDays} />
  </section><section className="panel prosePanel"><h2>Organization operations</h2><p>Manage organization access, employee capacity, tracking rules and subscription plans.</p><div className="actionsRow"><button className="primaryButton" onClick={() => setActivePage("organizations")}>Manage organizations</button><button className="secondaryButton" onClick={() => setActivePage("plans")}>Subscription plans</button><button className="secondaryButton" onClick={() => setActivePage("insights")}>View insights</button></div></section></div>;
}

function OrganizationsPage({ insights }) {
  const [query, setQuery] = useState(initialQuery);
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [message, setMessage] = useState("");
  const { data, loading, error } = useLoad(() => api.listOrganizations(query), [JSON.stringify(query), refresh]);
  const reload = (text) => { setMessage(text); setRefresh((n) => n + 1); };
  if (selected) return <OrganizationDetail orgId={selected} onBack={() => { setSelected(null); reload(""); }} />;
  return <section className="panel"><div className="sectionHead"><div><h2>{insights ? "Operational insights" : "Organizations"}</h2><p>{data?.pagination.total ?? "…"} organizations · {insights ? "Attendance and enrollment coverage" : "Access, administrators and subscriptions"}</p></div>{!insights ? <button className="primaryButton" onClick={() => setDialog({ type: "create" })}>Create organization</button> : null}</div>
    {message ? <div className="notice" role="status">{message}</div> : null}
    <ListingTools query={query} onChange={setQuery} sortOptions={[["created_at", "Created date"], ["org_name", "Organization name"], ["org_code", "Code"], ["admin_email", "Admin email"], ["users_count", "Employee count"]]} />
    {error ? <Notice text={error} /> : null}{loading ? <Loading /> : data ? <><DataTable columns={insights ? ["Organization", "Admin", "Employee usage", "Face profiles", "Today records", "Status"] : ["Organization", "Code", "Contact", "Subscription", "Employees", "Status", "Created", "Actions"]} rows={data.items.map((org) => insights ? [org.org_name, org.admin_name || "Unassigned", `${org.users_count}/${org.max_users}`, org.face_profiles, org.attendance_today, <Badge active={org.is_active}>{org.is_active ? "Active" : "Inactive"}</Badge>] : [<strong>{org.org_name}</strong>, org.org_code, <span>{org.admin_name}<br /><span className="muted">{org.admin_email}</span></span>, <span>{org.subscription?.plan?.name || "Unassigned"}<br /><small className="muted">{subscriptionStatus(org.subscription)}</small></span>, `${org.users_count}/${org.max_users}`, <Badge active={org.is_active}>{org.is_active ? "Active" : "Inactive"}</Badge>, dateLabel(org.created_at), <div className="actionsRow"><button className="secondaryButton" onClick={() => setSelected(org.org_id)}>View / Edit</button><button className="secondaryButton" onClick={() => setDialog({ type: "assign", org })}>Assign plan</button><button className={org.is_active ? "dangerButton" : "secondaryButton"} onClick={() => setDialog({ type: "toggle", org })}>{org.is_active ? "Deactivate" : "Activate"}</button></div>])} /><PaginationControls pagination={data.pagination} onPageChange={(page) => setQuery({ ...query, page })} onPageSizeChange={(page_size) => setQuery({ ...query, page_size, page: 1 })} /></> : null}
    {dialog?.type === "create" ? <OrganizationForm onClose={() => setDialog(null)} onSaved={() => { setDialog(null); reload("Organization created."); }} /> : null}
    {dialog?.type === "assign" ? <AssignmentModal org={dialog.org} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); reload("Subscription assigned."); }} /> : null}
    {dialog?.type === "toggle" ? <ConfirmAction title={`${dialog.org.is_active ? "Deactivate" : "Activate"} organization?`} description={`${dialog.org.org_name}: ${dialog.org.is_active ? "all administrators and employees will lose access" : "organization access will be restored"}.`} onClose={() => setDialog(null)} onConfirm={async () => { await api.toggleOrg(dialog.org.org_id); reload("Organization status updated."); }} /> : null}
  </section>;
}

function OrganizationDetail({ orgId, onBack }) {
  const [refresh, setRefresh] = useState(0), [page, setPage] = useState(1), [pageSize, setPageSize] = useState(10);
  const [dialog, setDialog] = useState(null), [message, setMessage] = useState("");
  const { data, loading, error } = useLoad(() => api.superadminOrg(orgId, { users_page: page, users_page_size: pageSize }), [orgId, refresh, page, pageSize]);
  // Keep dialogs mounted during background reloads so draft values stay intact.
  if (!data && loading) return <Loading />;
  if (!data && error) return <Notice text={error} />;
  if (!data) return null;
  return <div className="stack"><div className="sectionHead"><div><h2>{data.org.org_name}</h2><p>{data.org.org_code} · Organization details</p></div><div className="actionsRow"><button className="secondaryButton" onClick={onBack}>Back to organizations</button><button className="primaryButton" onClick={() => setDialog("edit")}>Edit organization</button><button className="secondaryButton" onClick={() => setDialog("assign")}>Assign plan</button></div></div>
    {message ? <div className="notice" role="status">{message}</div> : null}{error ? <Notice text={error} /> : null}
    <section className="statsGrid"><Stat label="Employees" value={`${data.summary.users_count}/${data.summary.user_limit}`} detail={`${data.summary.capacity_used_percent}% capacity used`} icon={Users} /><Stat label="Active employees" value={data.summary.active_users} detail={`${data.summary.inactive_users} inactive`} icon={Users} /><Stat label="Face coverage" value={`${data.summary.face_coverage_percent}%`} detail={`${data.summary.face_profiles} enrolled`} icon={ShieldCheck} /><Stat label="Today records" value={data.summary.attendance_today} detail="Attendance events" icon={CalendarDays} /></section>
    <div className="splitPanels"><section className="panel detailPanel"><h2>Administrator</h2><dl><dt>Name</dt><dd>{data.admin.name || "Unassigned"}</dd><dt>Email</dt><dd>{data.admin.email || "—"}</dd><dt>Status</dt><dd>{data.org.is_active ? "Active organization" : "Inactive organization"}</dd><dt>Subscription</dt><dd>{data.org.subscription?.plan?.name || "Unassigned"}</dd><dt>Subscription status</dt><dd>{subscriptionStatus(data.org.subscription)}</dd></dl></section><section className="panel detailPanel"><div className="sectionHead"><h2>Tracking rules</h2><button type="button" className="secondaryButton" onClick={() => setDialog("edit")}>Edit tracking rules</button></div><dl><dt>Auto checkout</dt><dd>{data.tracking_settings.auto_checkout_enabled ? "Enabled" : "Disabled"}</dd><dt>Timeout</dt><dd>{data.tracking_settings.tracking_timeout_hours} hours</dd><dt>GPS interval</dt><dd>{data.tracking_settings.tracking_interval_minutes} minutes</dd></dl></section></div>
    <section className="panel"><h2>Employees</h2><DataTable columns={["Employee ID", "Name", "Email", "Face", "Status"]} rows={data.users.map((user) => [user.employee_id, user.employee_name, user.email, user.face_enrolled ? "Enrolled" : "Pending", user.is_active ? "Active" : "Inactive"])} /><PaginationControls pagination={data.users_pagination} onPageChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} /></section>
    {data.org.subscription?.plan ? <section className="panel"><h2>Subscription pricing</h2><div className="priceSummary"><span>Current total per {data.org.subscription.plan.billing_cycle === "yearly" ? "year" : "month"}</span><strong>{money(data.org.subscription.plan, totalMinor(data.org.subscription.plan, data.summary.users_count))}</strong><small>{money(data.org.subscription.plan)} base + {money(data.org.subscription.plan, data.org.subscription.plan.per_user_price_minor || 0)} × {data.summary.users_count} registered employees</small></div><button className="secondaryButton" onClick={() => setDialog("assign")}>Change pricing</button></section> : null}
    {dialog === "edit" ? <OrganizationForm detail={data} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); setMessage("Organization updated."); setRefresh((n) => n + 1); }} /> : null}
    {dialog === "assign" ? <AssignmentModal org={{ ...data.org, users_count: data.summary.users_count }} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); setMessage("Subscription assigned."); setRefresh((n) => n + 1); }} /> : null}
  </div>;
}

function OrganizationForm({ detail, onClose, onSaved }) {
  const initial = { org_name: detail?.org.org_name || "", org_code: detail?.org.org_code || "", max_users: detail?.org.max_users || 10, admin_name: detail?.admin.name || "", admin_email: detail?.admin.email || "", admin_password: "", auto_checkout_enabled: detail?.tracking_settings.auto_checkout_enabled ?? true, tracking_timeout_hours: detail?.tracking_settings.tracking_timeout_hours ?? 4, tracking_interval_minutes: detail?.tracking_settings.tracking_interval_minutes ?? 30 };
  const [form, setForm] = useState(initial), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [configureSubscription, setConfigureSubscription] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState(detail?.org.subscription?.plan || null);
  const [pricing, setPricing] = useState(() => pricingForm(detail?.org.subscription?.plan));
  const [starts, setStarts] = useState(() => localDate(detail?.org.subscription?.starts_at || new Date()));
  const [ends, setEnds] = useState(() => detail?.org.subscription?.ends_at ? localDate(detail.org.subscription.ends_at) : "");
  const field = (name, value) => setForm({ ...form, [name]: value });
  async function save(e) { e.preventDefault(); setBusy(true); setError(""); try { const payload = { ...form, org_name: form.org_name.trim(), org_code: form.org_code.trim(), admin_name: form.admin_name.trim(), admin_email: form.admin_email.trim(), max_users: Number(form.max_users), tracking_timeout_hours: Number(form.tracking_timeout_hours), tracking_interval_minutes: Number(form.tracking_interval_minutes) }; if (!payload.org_name || !payload.org_code || !payload.admin_name) throw new Error("Organization details cannot be blank."); if (configureSubscription) { if (!selectedPlan) throw new Error("Choose a subscription plan."); payload.subscription = assignmentPayload(selectedPlan, pricingPayload(pricing), starts, ends); } if (detail) await api.updateOrg(detail.org.org_id, payload); else await api.createOrg(payload); onSaved(); } catch (err) { setError(err.message); } finally { setBusy(false); } }
  return <Modal title={detail ? "Edit organization" : "Create organization"} onClose={onClose} dirty={configureSubscription || JSON.stringify(initial) !== JSON.stringify(form)} busy={busy}><form onSubmit={save}><fieldset className="fieldsetReset formColumns" disabled={busy}>
    <label>Organization name<input required maxLength={160} value={form.org_name} onChange={(e) => field("org_name", e.target.value)} /></label><label>Organization code<input required maxLength={100} value={form.org_code} onChange={(e) => field("org_code", e.target.value)} /></label>
    <label>Employee limit<input required type="number" min={detail?.summary.users_count || 1} value={form.max_users} onChange={(e) => field("max_users", e.target.value)} /></label><label>Admin name<input required maxLength={160} value={form.admin_name} onChange={(e) => field("admin_name", e.target.value)} /></label>
    <label>Admin email<input required type="email" maxLength={254} value={form.admin_email} onChange={(e) => field("admin_email", e.target.value)} /></label><label>{detail ? "New admin password (optional)" : "Admin password"}<input type="password" autoComplete="new-password" required={!detail} value={form.admin_password} onChange={(e) => field("admin_password", e.target.value)} /></label>
    {detail ? <><label className="checkRow fullWidth"><input type="checkbox" checked={form.auto_checkout_enabled} onChange={(e) => field("auto_checkout_enabled", e.target.checked)} />Automatic checkout enabled</label><label>Checkout timeout (hours)<input required type="number" min="0.25" step="0.25" value={form.tracking_timeout_hours} onChange={(e) => field("tracking_timeout_hours", e.target.value)} /></label><label>GPS interval (minutes)<input required type="number" min="1" value={form.tracking_interval_minutes} onChange={(e) => field("tracking_interval_minutes", e.target.value)} /></label></> : null}
    <label className="checkRow fullWidth"><input type="checkbox" checked={configureSubscription} onChange={(e) => setConfigureSubscription(e.target.checked)} />{detail ? "Change subscription and pricing" : "Assign subscription and pricing"}</label>
    {configureSubscription ? <><PlanPicker selected={selectedPlan} disabled={busy} onSelect={(plan) => { setSelectedPlan(plan); setPricing(pricingForm(plan)); }} /><label>Subscription starts<input required type="date" value={starts} onChange={(e) => setStarts(e.target.value)} /></label><label>Subscription ends (optional)<input type="date" min={starts} value={ends} onChange={(e) => setEnds(e.target.value)} /></label>{selectedPlan ? <PricingFields form={pricing} onChange={setPricing} users={detail?.summary.users_count || 0} currency={selectedPlan.currency} /> : null}</> : null}
  </fieldset>{error ? <Notice text={error} /> : null}<div className="modalFooter"><button type="button" className="secondaryButton" disabled={busy} data-close-modal>Cancel</button><button className="primaryButton" disabled={busy}>{busy ? "Saving…" : detail ? "Save changes" : "Create organization"}</button></div></form></Modal>;
}
