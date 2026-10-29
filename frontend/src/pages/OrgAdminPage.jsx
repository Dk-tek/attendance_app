import { useState } from "react";
import { CalendarDays, CheckCircle2, ShieldCheck, Users } from "lucide-react";
import { api } from "../api";
import { DataTable } from "../components/DataTable";
import { Loading, Notice } from "../components/Feedback";
import { PaginationControls } from "../components/PaginationControls";
import { Stat } from "../components/Stat";
import { useLoad } from "../hooks/useLoad";
import { AttendanceExplorer } from "./AttendanceExplorer";

export function OrgAdminPage({ activePage }) {
  const [refresh, setRefresh] = useState(0);
  const [usersPage, setUsersPage] = useState(1);
  const { data, error, loading } = useLoad(
    () => api.orgDashboard({ users_page: usersPage, users_page_size: 10 }),
    [refresh, usersPage],
  );
  const [form, setForm] = useState({ employee_id: "", employee_name: "", email: "", password: "" });
  const [message, setMessage] = useState("");

  async function createUser(event) {
    event.preventDefault();
    setMessage("");
    try {
      await api.createUser(form);
      setForm({ employee_id: "", employee_name: "", email: "", password: "" });
      setMessage("User created. Face enrollment can be added from the mobile/API flow.");
      setRefresh((value) => value + 1);
    } catch (err) {
      setMessage(err.message);
    }
  }

  if (loading) return <Loading />;
  if (error) return <Notice text={error} />;

  return (
    <div className="stack">
      {activePage === "overview" ? <OrgOverview data={data} /> : null}
      {activePage === "users" ? (
        <section className="contentGrid">
          <form className="panel formGrid" onSubmit={createUser}>
            <h2>Create employee</h2>
            <input placeholder="Employee ID" value={form.employee_id} onChange={(event) => setForm({ ...form, employee_id: event.target.value })} required />
            <input placeholder="Employee name" value={form.employee_name} onChange={(event) => setForm({ ...form, employee_name: event.target.value })} required />
            <input type="email" placeholder="Email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
            <input type="password" placeholder="Password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required />
            {message ? <div className="notice">{message}</div> : null}
            <button className="primaryButton" type="submit">Create user</button>
          </form>
          <UserManagementTable
            data={data}
            onRefresh={() => setRefresh((value) => value + 1)}
            onPageChange={setUsersPage}
          />
        </section>
      ) : null}
      {activePage === "attendance" ? <AttendanceExplorer users={data?.all_users || data?.users || []} /> : null}
      {activePage === "settings" ? <TrackingSettings data={data} /> : null}
    </div>
  );
}

function OrgOverview({ data }) {
  return (
    <>
      <section className="statsGrid">
        <Stat label="Users" value={`${data.summary.users_count}/${data.summary.user_limit}`} detail={`${data.summary.capacity_used_percent}% capacity`} icon={Users} />
        <Stat label="Active users" value={data.summary.active_users} detail={`${data.summary.inactive_users} inactive`} icon={CheckCircle2} />
        <Stat label="Face coverage" value={`${data.summary.face_coverage_percent}%`} detail={`${data.summary.face_profiles} enrolled`} icon={ShieldCheck} />
        <Stat label="Tracking now" value={data.summary.active_tracking_sessions} detail="Active check-in sessions" icon={CalendarDays} />
      </section>
      <section className="panel prosePanel">
        <h2>Real-time tracking workspace</h2>
        <p>
          Monitor employee attendance activity, review location trails, and maintain face enrollment coverage for efficient field operations.
        </p>
      </section>
    </>
  );
}

function TrackingSettings({ data }) {
  const settings = data.tracking_settings || {};
  return (
    <section className="contentGrid">
      <section className="panel detailPanel">
        <h2>Tracking settings</h2>
        <dl>
          <dt>Auto checkout</dt>
          <dd>{settings.auto_checkout_enabled ? "Enabled" : "Disabled"}</dd>
          <dt>Timeout</dt>
          <dd>{settings.tracking_timeout_hours ?? 4} hours</dd>
          <dt>GPS interval</dt>
          <dd>{settings.tracking_interval_minutes ?? 30} minutes</dd>
        </dl>
        <div className="notice">Only superadmin can edit these values.</div>
      </section>
      <section className="panel prosePanel">
        <h2>Auto checkout rule</h2>
        <p>
          When an employee checks in, TrackPulse opens an active tracking session. If the employee does not check out before the configured timeout,
          the backend creates an automatic checkout record with a remark.
        </p>
        <p>
          If GPS or network tracking fails, the mobile app can send a failed tracking event with a remark. If the phone is fully offline, it should save
          that event locally and sync it when connectivity returns.
        </p>
      </section>
    </section>
  );
}

function UserManagementTable({ data, onRefresh, onPageChange }) {
  return (
    <div className="panel">
      <div className="sectionHead">
        <h2>Registered users</h2>
        <span>{data.users.length} employees</span>
      </div>
      <DataTable
        columns={["Employee ID", "Name", "Email", "Face", "Status", "Action"]}
        rows={data.users.map((user) => [
          user.employee_id,
          user.employee_name,
          user.email,
          user.face_enrolled ? "Enrolled" : "Pending",
          user.is_active ? "Active" : "Inactive",
          <button className={user.is_active ? "dangerButton" : "secondaryButton"} onClick={() => api.toggleUser(user.user_id).then(onRefresh)}>
            {user.is_active ? "Deactivate" : "Activate"}
          </button>
        ])}
      />
      <PaginationControls pagination={data.users_pagination} onPageChange={onPageChange} />
    </div>
  );
}
