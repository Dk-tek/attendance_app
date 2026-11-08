import { CalendarDays, CheckCircle2, ShieldCheck, Users } from "lucide-react";
import { api } from "../api";
import { DataTable } from "../components/DataTable";
import { Loading, Notice } from "../components/Feedback";
import { Stat } from "../components/Stat";
import { useLoad } from "../hooks/useLoad";
import { AttendanceExplorer } from "./AttendanceExplorer";
import { EmployeesPage } from "./EmployeesPage";
import { PolicyPage } from "./PolicyPage";
import { SubscriptionPage } from "./SubscriptionPage";

export function OrgAdminPage({ activePage }) {
  if (activePage === "users") return <EmployeesPage />;
  if (["terms", "privacy"].includes(activePage)) return <PolicyPage key={activePage} kind={activePage} />;
  if (["subscription", "organization"].includes(activePage)) return <SubscriptionPage />;
  return <OrgDashboard activePage={activePage} />;
}

function OrgDashboard({ activePage }) {
  const { data, error, loading } = useLoad(() => api.orgDashboard({ users_page_size: 10 }), []);
  if (loading) return <Loading />;
  if (error) return <Notice text={error} />;
  if (activePage === "attendance") return <AttendanceExplorer users={data.all_users || data.users || []} />;
  if (activePage === "settings") return <TrackingSettings data={data} />;
  return <div className="stack"><section className="statsGrid">
    <Stat label="Employees" value={`${data.summary.users_count}/${data.summary.user_limit}`} detail={`${data.summary.capacity_used_percent}% capacity used`} icon={Users} />
    <Stat label="Active employees" value={data.summary.active_users} detail={`${data.summary.inactive_users} inactive`} icon={CheckCircle2} />
    <Stat label="Face coverage" value={`${data.summary.face_coverage_percent}%`} detail={`${data.summary.face_profiles} enrolled`} icon={ShieldCheck} />
    <Stat label="Tracking now" value={data.summary.active_tracking_sessions} detail={`${data.summary.attendance_today} attendance events today`} icon={CalendarDays} />
  </section><div className="splitPanels"><section className="panel detailPanel"><h2>{data.org.org_name}</h2><dl><dt>Organization code</dt><dd>{data.org.org_code}</dd><dt>Status</dt><dd>{data.summary.status}</dd><dt>Employee usage</dt><dd>{data.summary.users_count} of {data.summary.user_limit}</dd><dt>Subscription</dt><dd>{data.org.subscription?.plan?.name || "No plan assigned"}</dd></dl></section><section className="panel prosePanel"><h2>Enrollment readiness</h2><p>{data.summary.face_profiles} face profiles are enrolled for {data.summary.users_count} employees.</p><progress aria-label="Face enrollment coverage" max="100" value={data.summary.face_coverage_percent} /><p>Face enrollment is managed through the existing mobile and API workflow.</p></section></div><section className="panel"><div className="sectionHead"><h2>Recent attendance</h2><span className="muted">Latest {data.recent_attendance.length} events</span></div><DataTable columns={["Employee", "Event", "Time", "Remark"]} rows={data.recent_attendance.map((row) => [row.employee_name || row.employee_id, row.attendance_type, row.display_timestamp || row.timestamp, row.remark || "—"])} /></section></div>;
}

function TrackingSettings({ data }) {
  const settings = data.tracking_settings || {};
  return <section className="splitPanels"><section className="panel detailPanel"><h2>Tracking configuration</h2><dl><dt>Auto checkout</dt><dd>{settings.auto_checkout_enabled ? "Enabled" : "Disabled"}</dd><dt>Timeout</dt><dd>{settings.tracking_timeout_hours ?? "—"} hours</dd><dt>GPS interval</dt><dd>{settings.tracking_interval_minutes ?? "—"} minutes</dd></dl><div className="notice">These settings are managed by your Super Admin.</div></section><section className="panel prosePanel"><h2>How automatic checkout works</h2><p>An employee check-in opens an active tracking session. If the employee does not check out before the configured timeout, the backend records an automatic checkout with a remark.</p><p>GPS or network failures can be reported by the mobile app with a remark. Offline events are saved locally and synced when connectivity returns.</p></section></section>;
}
