import { useState } from "react";
import { Plus } from "lucide-react";
import { api } from "../api";
import { useLoad } from "../hooks/useLoad";
import { DataTable } from "../components/DataTable";
import { PaginationControls } from "../components/PaginationControls";
import { Loading, Notice } from "../components/Feedback";
import { Modal, ConfirmAction } from "../components/Modal";
import { Badge, dateLabel, initialQuery, ListingTools } from "../components/Listing";

export function EmployeesPage() {
  const [query, setQuery] = useState(initialQuery);
  const [refresh, setRefresh] = useState(0);
  const [dialog, setDialog] = useState(null);
  const [message, setMessage] = useState("");
  const { data, loading, error } = useLoad(() => api.listUsers(query), [JSON.stringify(query), refresh]);
  const reload = (text) => { setMessage(text); setRefresh((n) => n + 1); };
  return <section className="panel">
    <div className="sectionHead"><div><h2>Employees</h2><p>{data?.pagination.total ?? "…"} registered employees · Manage access and enrollment</p></div><button className="primaryButton" onClick={() => setDialog({ type: "create" })}><Plus size={16} />Create employee</button></div>
    {message ? <div className="notice" role="status">{message}</div> : null}
    <ListingTools query={query} onChange={setQuery} sortOptions={[["created_at", "Created date"], ["employee_name", "Name"], ["employee_id", "Employee ID"], ["email", "Email"]]} />
    {error ? <Notice text={error} /> : null}
    {loading ? <Loading /> : data ? <><DataTable columns={["Employee ID", "Employee", "Email", "Face enrollment", "Status", "Actions"]} rows={data.items.map((user) => [user.employee_id, <strong>{user.employee_name}</strong>, user.email, <Badge active={user.face_enrolled}>{user.face_enrolled ? "Enrolled" : "Pending"}</Badge>, <Badge active={user.is_active}>{user.is_active ? "Active" : "Inactive"}</Badge>, <div className="actionsRow"><button className="secondaryButton" onClick={() => setDialog({ type: "view", user })}>View</button><button className="secondaryButton" onClick={() => setDialog({ type: "edit", user })}>Edit</button><button className={user.is_active ? "dangerButton" : "secondaryButton"} onClick={() => setDialog({ type: "toggle", user })}>{user.is_active ? "Deactivate" : "Activate"}</button></div>])} /><PaginationControls pagination={data.pagination} onPageChange={(page) => setQuery({ ...query, page })} onPageSizeChange={(page_size) => setQuery({ ...query, page_size, page: 1 })} /></> : null}
    {dialog?.type === "view" ? <Modal title="Employee details" onClose={() => setDialog(null)}><div className="detailPanel"><dl>{[["Employee ID", dialog.user.employee_id], ["Name", dialog.user.employee_name], ["Email", dialog.user.email], ["Status", dialog.user.is_active ? "Active" : "Inactive"], ["Face enrollment", dialog.user.face_enrolled ? "Enrolled" : "Pending"], ["Created", dateLabel(dialog.user.created_at)]].map(([label, value]) => <div key={label} style={{ display: "contents" }}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></div></Modal> : null}
    {["create", "edit"].includes(dialog?.type) ? <EmployeeForm user={dialog.user} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); reload(dialog.type === "edit" ? "Employee updated." : "Employee created. Enroll their face through the existing mobile flow."); }} /> : null}
    {dialog?.type === "toggle" ? <ConfirmAction title={`${dialog.user.is_active ? "Deactivate" : "Activate"} employee?`} description={`${dialog.user.employee_name} will ${dialog.user.is_active ? "lose" : "regain"} access to this organization.`} onClose={() => setDialog(null)} onConfirm={async () => { await api.toggleUser(dialog.user.user_id); reload("Employee status updated."); }} /> : null}
  </section>;
}

function EmployeeForm({ user, onClose, onSaved }) {
  const initial = { employee_id: user?.employee_id || "", employee_name: user?.employee_name || "", email: user?.email || "", password: "" };
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const payload = { ...form, employee_id: form.employee_id.trim(), employee_name: form.employee_name.trim(), email: form.email.trim() };
      if (!payload.employee_id || !payload.employee_name) throw new Error("Employee ID and name cannot be blank.");
      if (user) await api.updateUser(user.user_id, { employee_name: payload.employee_name, email: payload.email, password: payload.password });
      else await api.createUser(payload);
      onSaved();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <Modal title={user ? "Edit employee" : "Create employee"} onClose={onClose} busy={busy} dirty={JSON.stringify(form) !== JSON.stringify(initial)}><form className="formGrid" onSubmit={save}><fieldset disabled={busy} className="formGrid fieldsetReset">
    <label>Employee ID<input required maxLength={100} value={form.employee_id} disabled={!!user} onChange={(e) => setForm({ ...form, employee_id: e.target.value })} /></label>
    {user ? <small className="muted">Employee IDs stay fixed to preserve attendance and tracking history.</small> : null}
    <label>Full name<input required maxLength={160} value={form.employee_name} onChange={(e) => setForm({ ...form, employee_name: e.target.value })} /></label>
    <label>Email address<input required type="email" maxLength={254} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
    <label>{user ? "New password (optional)" : "Password"}<input autoComplete="new-password" type="password" required={!user} maxLength={256} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
    {error ? <Notice text={error} /> : null}
    <div className="modalFooter"><button type="button" className="secondaryButton" data-close-modal>Cancel</button><button className="primaryButton" type="submit">{busy ? "Saving…" : user ? "Save changes" : "Create employee"}</button></div>
  </fieldset></form></Modal>;
}
