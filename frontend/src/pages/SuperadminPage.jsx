import { useState } from "react";
import { Building2, CalendarDays, ShieldCheck, Users } from "lucide-react";
import { api } from "../api";
import { DataTable } from "../components/DataTable";
import { Loading, Notice } from "../components/Feedback";
import { PaginationControls } from "../components/PaginationControls";
import { Stat } from "../components/Stat";
import { useLoad } from "../hooks/useLoad";

const emptyOrgForm = {
  org_name: "",
  org_code: "",
  max_users: 10,
  admin_name: "",
  admin_email: "",
  admin_password: ""
};

export function SuperadminPage({ activePage, setActivePage }) {
  const [refresh, setRefresh] = useState(0);
  const [orgPage, setOrgPage] = useState(1);
  const [selectedOrgId, setSelectedOrgId] = useState("");
  const { data, error, loading } = useLoad(() => api.superadminDashboard({ page: orgPage, page_size: 10 }), [refresh, orgPage]);

  if (loading) return <Loading />;
  if (error) return <Notice text={error} />;

  if (selectedOrgId) {
    return (
      <SuperadminOrgDetail
        orgId={selectedOrgId}
        onBack={() => {
          setSelectedOrgId("");
          setActivePage("organizations");
          setRefresh((value) => value + 1);
        }}
      />
    );
  }

  return (
    <div className="stack">
      {(activePage === "overview" || activePage === "insights") ? <SuperadminStats data={data} /> : null}
      {activePage === "overview" ? <SummaryPanel data={data} setActivePage={setActivePage} /> : null}
      {activePage === "organizations" ? (
        <section className="contentGrid">
          <CreateOrganizationForm onCreated={() => setRefresh((value) => value + 1)} />
          <OrganizationList
            data={data}
            onView={setSelectedOrgId}
            onRefresh={() => setRefresh((value) => value + 1)}
            onPageChange={setOrgPage}
          />
        </section>
      ) : null}
      {activePage === "insights" ? <InsightsPanel data={data} /> : null}
    </div>
  );
}

function SuperadminStats({ data }) {
  return (
    <section className="statsGrid">
      <Stat label="Organizations" value={data.summary.organizations} detail={`${data.summary.active_organizations} active`} icon={Building2} />
      <Stat label="Users" value={data.summary.users} detail="Across all organizations" icon={Users} />
      <Stat label="Face profiles" value={data.summary.face_profiles} detail="Ready for auth" icon={ShieldCheck} />
      <Stat label="Today records" value={data.summary.attendance_today} detail="Check-in and check-out" icon={CalendarDays} />
    </section>
  );
}

function SummaryPanel({ data, setActivePage }) {
  return (
    <section className="panel prosePanel">
      <h2>Attendance monitoring command center</h2>
      <p>
        TrackPulse keeps organization attendance, face profile readiness, and employee activity visible from one control layer.
        Use organization pages to manage admins and users, and insights to review operational coverage.
      </p>
      <div className="actionsRow">
        <button className="primaryButton" onClick={() => setActivePage("organizations")}>Manage organizations</button>
        <button className="secondaryButton" onClick={() => setActivePage("insights")}>View insights</button>
      </div>
    </section>
  );
}

function OrganizationList({ data, onView, onRefresh, onPageChange }) {
  return (
    <div className="panel">
      <div className="sectionHead">
        <h2>Organizations</h2>
        <span>{data.pagination?.total ?? data.orgs.length} total</span>
      </div>
      <div className="orgList">
        {data.orgs.map((org) => (
          <article className="rowCard" key={org.org_id}>
            <div>
              <strong>{org.org_name}</strong>
              <p>{org.org_code} - {org.admin_name || "No admin"} - {org.admin_email}</p>
            </div>
            <div className="rowMeta">
              <span>{org.users_count}/{org.max_users} users</span>
              <span>{org.face_profiles} faces</span>
              <span>{org.attendance_today} today</span>
              <button className="secondaryButton" onClick={() => onView(org.org_id)}>View</button>
              <button className={org.is_active ? "dangerButton" : "secondaryButton"} onClick={() => api.toggleOrg(org.org_id).then(onRefresh)}>
                {org.is_active ? "Deactivate" : "Activate"}
              </button>
            </div>
          </article>
        ))}
      </div>
      <PaginationControls pagination={data.pagination} onPageChange={onPageChange} />
    </div>
  );
}

function InsightsPanel({ data }) {
  const orgs = data.all_orgs || data.orgs;
  return (
    <section className="panel">
      <div className="sectionHead">
        <h2>Operational insights</h2>
        <span>Teal Ops</span>
      </div>
      <DataTable
        columns={["Organization", "Admin", "Capacity", "Face coverage", "Today", "Status"]}
        rows={orgs.map((org) => [
          org.org_name,
          org.admin_name || "Not assigned",
          `${org.users_count}/${org.max_users}`,
          `${org.face_profiles} profiles`,
          org.attendance_today,
          org.is_active ? "Active" : "Inactive"
        ])}
      />
    </section>
  );
}

function CreateOrganizationForm({ onCreated }) {
  const [form, setForm] = useState(emptyOrgForm);
  const [message, setMessage] = useState("");

  async function createOrg(event) {
    event.preventDefault();
    setMessage("");
    try {
      await api.createOrg({ ...form, max_users: Number(form.max_users) });
      setForm(emptyOrgForm);
      setMessage("Organization created.");
      onCreated();
    } catch (err) {
      setMessage(err.message);
    }
  }

  return (
    <form className="panel formGrid" onSubmit={createOrg}>
      <h2>Onboard organization</h2>
      <input placeholder="Organization name" value={form.org_name} onChange={(event) => setForm({ ...form, org_name: event.target.value })} required />
      <input placeholder="Organization code" value={form.org_code} onChange={(event) => setForm({ ...form, org_code: event.target.value })} required />
      <input type="number" min="1" placeholder="Max users" value={form.max_users} onChange={(event) => setForm({ ...form, max_users: event.target.value })} required />
      <input placeholder="Admin name" value={form.admin_name} onChange={(event) => setForm({ ...form, admin_name: event.target.value })} required />
      <input type="email" placeholder="Admin email" value={form.admin_email} onChange={(event) => setForm({ ...form, admin_email: event.target.value })} required />
      <input type="password" placeholder="Admin password" value={form.admin_password} onChange={(event) => setForm({ ...form, admin_password: event.target.value })} required />
      {message ? <div className="notice">{message}</div> : null}
      <button className="primaryButton" type="submit">Create organization</button>
    </form>
  );
}

function SuperadminOrgDetail({ orgId, onBack }) {
  const [refresh, setRefresh] = useState(0);
  const [usersPage, setUsersPage] = useState(1);
  const { data, error, loading } = useLoad(
    () => api.superadminOrg(orgId, { users_page: usersPage, users_page_size: 10 }),
    [orgId, refresh, usersPage],
  );

  if (loading) return <Loading />;
  if (error) return <Notice text={error} />;

  return (
    <div className="stack">
      <div className="sectionHead">
        <div>
          <p className="eyebrow">Organization detail</p>
          <h2>{data.org.org_name}</h2>
        </div>
        <button className="secondaryButton" onClick={onBack}>Back to organizations</button>
      </div>

      <section className="statsGrid">
        <Stat label="Users" value={`${data.summary.users_count}/${data.summary.user_limit}`} detail={`${data.summary.capacity_used_percent}% capacity`} icon={Users} />
        <Stat label="Active users" value={data.summary.active_users} detail={`${data.summary.inactive_users} inactive`} icon={Users} />
        <Stat label="Face coverage" value={`${data.summary.face_coverage_percent}%`} detail={`${data.summary.face_profiles} enrolled`} icon={ShieldCheck} />
        <Stat label="Today records" value={data.summary.attendance_today} detail="Attendance events" icon={CalendarDays} />
      </section>

      <section className="contentGrid">
        <EditOrganizationForm detail={data} onSaved={() => setRefresh((value) => value + 1)} />
        <div className="stack">
          <section className="panel detailPanel">
            <div className="sectionHead">
              <h2>Admin</h2>
              <span>{data.admin.is_active === false ? "Inactive" : "Active"}</span>
            </div>
            <dl>
              <dt>Name</dt>
              <dd>{data.admin.name || "Not assigned"}</dd>
              <dt>Email</dt>
              <dd>{data.admin.email || "Not assigned"}</dd>
              <dt>Admin ID</dt>
              <dd>{data.admin.admin_id || "-"}</dd>
            </dl>
          </section>

          <DataTable
            columns={["Employee ID", "Name", "Email", "Face", "Status"]}
            rows={data.users.map((user) => [
              user.employee_id,
              user.employee_name,
              user.email,
              user.face_enrolled ? "Enrolled" : "Pending",
              user.is_active ? "Active" : "Inactive"
            ])}
          />
          <PaginationControls pagination={data.users_pagination} onPageChange={setUsersPage} />
        </div>
      </section>
    </div>
  );
}

function EditOrganizationForm({ detail, onSaved }) {
  const [form, setForm] = useState({
    org_name: detail.org.org_name || "",
    org_code: detail.org.org_code || "",
    max_users: detail.org.max_users || 1,
    admin_name: detail.admin.name || "",
    admin_email: detail.admin.email || "",
    admin_password: "",
    auto_checkout_enabled: detail.tracking_settings?.auto_checkout_enabled ?? true,
    tracking_timeout_hours: detail.tracking_settings?.tracking_timeout_hours ?? 4,
    tracking_interval_minutes: detail.tracking_settings?.tracking_interval_minutes ?? 30
  });
  const [message, setMessage] = useState("");

  async function save(event) {
    event.preventDefault();
    setMessage("");
    try {
      await api.updateOrg(detail.org.org_id, {
        ...form,
        max_users: Number(form.max_users),
        tracking_timeout_hours: Number(form.tracking_timeout_hours),
        tracking_interval_minutes: Number(form.tracking_interval_minutes)
      });
      setMessage("Organization updated.");
      setForm((current) => ({ ...current, admin_password: "" }));
      onSaved();
    } catch (err) {
      setMessage(err.message);
    }
  }

  return (
    <form className="panel formGrid" onSubmit={save}>
      <h2>Edit organization</h2>
      <input placeholder="Organization name" value={form.org_name} onChange={(event) => setForm({ ...form, org_name: event.target.value })} required />
      <input placeholder="Organization code" value={form.org_code} onChange={(event) => setForm({ ...form, org_code: event.target.value })} required />
      <input type="number" min="1" placeholder="Max users" value={form.max_users} onChange={(event) => setForm({ ...form, max_users: event.target.value })} required />
      <input placeholder="Admin name" value={form.admin_name} onChange={(event) => setForm({ ...form, admin_name: event.target.value })} required />
      <input type="email" placeholder="Admin email" value={form.admin_email} onChange={(event) => setForm({ ...form, admin_email: event.target.value })} required />
      <input type="password" placeholder="New admin password, optional" value={form.admin_password} onChange={(event) => setForm({ ...form, admin_password: event.target.value })} />
      <label className="checkRow">
        <input
          type="checkbox"
          checked={form.auto_checkout_enabled}
          onChange={(event) => setForm({ ...form, auto_checkout_enabled: event.target.checked })}
        />
        Auto checkout enabled
      </label>
      <label>
        Auto checkout after hours
        <input
          type="number"
          min="0.25"
          step="0.25"
          value={form.tracking_timeout_hours}
          onChange={(event) => setForm({ ...form, tracking_timeout_hours: event.target.value })}
          required
        />
      </label>
      <label>
        GPS tracking interval minutes
        <input
          type="number"
          min="1"
          value={form.tracking_interval_minutes}
          onChange={(event) => setForm({ ...form, tracking_interval_minutes: event.target.value })}
          required
        />
      </label>
      {message ? <div className="notice">{message}</div> : null}
      <button className="primaryButton" type="submit">Save changes</button>
    </form>
  );
}
