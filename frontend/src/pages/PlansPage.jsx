import { useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks/useLoad";
import { DataTable } from "../components/DataTable";
import { ListingTools, initialQuery, Badge, dateLabel } from "../components/Listing";
import { PaginationControls } from "../components/PaginationControls";
import { Modal, ConfirmAction } from "../components/Modal";
import { Loading, Notice } from "../components/Feedback";
import { money, totalMinor, PricingFields, pricingForm, pricingPayload } from "../components/Pricing";
import { PlanPicker, assignmentPayload, localDate } from "../components/PlanPicker";

function planPayload(plan) {
  return { name: plan.name.trim(), code: plan.code.trim().toLowerCase(), description: plan.description || "", price_minor: plan.price_minor, per_user_price_minor: plan.per_user_price_minor || 0, currency: plan.currency, billing_cycle: plan.billing_cycle, max_users: Number(plan.max_users), is_active: plan.is_active };
}

export function PlansPage() {
  const [query, setQuery] = useState(initialQuery);
  const [refresh, setRefresh] = useState(0);
  const [dialog, setDialog] = useState(null);
  const [message, setMessage] = useState("");
  const { data, loading, error } = useLoad(() => api.plans(query), [JSON.stringify(query), refresh]);
  const updated = (text) => { setMessage(text); setRefresh((n) => n + 1); };
  return <section className="panel">
    <div className="sectionHead"><div><h2>Subscription plans</h2><p>Base price + per-user pricing · {data?.pagination.total ?? "…"} plans</p></div><button className="primaryButton" onClick={() => setDialog({ type: "create" })}>Create plan</button></div>
    {message ? <div className="notice" role="status">{message}</div> : null}
    <ListingTools query={query} onChange={setQuery} sortOptions={[["created_at", "Created date"], ["name", "Plan name"], ["code", "Plan code"], ["price_minor", "Base price"], ["per_user_price_minor", "Price per user"], ["max_users", "User limit"]]} />
    {error ? <Notice text={error} /> : null}
    {loading ? <Loading /> : data ? <>
      <DataTable columns={["Plan", "Code", "Base price", "Per user", "Cycle", "User limit", "Total at limit", "Status", "Actions"]} rows={data.items.map((plan) => [
        <span><strong>{plan.name}</strong>{plan.description ? <small className="tableDescription">{plan.description}</small> : null}</span>, plan.code, money(plan), money(plan, plan.per_user_price_minor || 0), plan.billing_cycle, plan.max_users, money(plan, totalMinor(plan, plan.max_users)),
        <Badge active={plan.is_active}>{plan.is_active ? "Active" : "Inactive"}</Badge>,
        <div className="actionsRow"><button className="secondaryButton" onClick={() => setDialog({ type: "view", plan })}>View</button><button className="secondaryButton" onClick={() => setDialog({ type: "edit", plan })}>Edit</button><button className="secondaryButton" onClick={() => setDialog({ type: "toggle", plan })}>{plan.is_active ? "Deactivate" : "Activate"}</button>{!plan.is_active ? <button className="dangerButton" onClick={() => setDialog({ type: "delete", plan })}>Delete</button> : null}</div>
      ])} />
      <PaginationControls pagination={data.pagination} onPageChange={(page) => setQuery({ ...query, page })} onPageSizeChange={(page_size) => setQuery({ ...query, page_size, page: 1 })} />
    </> : null}
    {["create", "edit"].includes(dialog?.type) ? <PlanForm plan={dialog.plan} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); updated("Plan saved."); }} /> : null}
    {dialog?.type === "view" ? <Modal title={dialog.plan.name} onClose={() => setDialog(null)}><div className="detailPanel"><p>{dialog.plan.description}</p><dl><dt>Code</dt><dd>{dialog.plan.code}</dd><dt>Base price</dt><dd>{money(dialog.plan)}</dd><dt>Price per user</dt><dd>{money(dialog.plan, dialog.plan.per_user_price_minor || 0)}</dd><dt>Billing cycle</dt><dd>{dialog.plan.billing_cycle}</dd><dt>User limit</dt><dd>{dialog.plan.max_users}</dd><dt>Total at limit</dt><dd>{money(dialog.plan, totalMinor(dialog.plan, dialog.plan.max_users))}</dd><dt>Created</dt><dd>{dateLabel(dialog.plan.created_at)}</dd></dl></div></Modal> : null}
    {["toggle", "delete"].includes(dialog?.type) ? <ConfirmAction title={dialog.type === "delete" ? "Delete plan?" : `${dialog.plan.is_active ? "Deactivate" : "Activate"} plan?`} description={dialog.type === "delete" ? `Delete ${dialog.plan.name}? Assigned plans cannot be deleted.` : `Change availability of ${dialog.plan.name} for new assignments? Existing organization pricing stays unchanged.`} onClose={() => setDialog(null)} onConfirm={async () => { if (dialog.type === "delete") await api.deletePlan(dialog.plan.plan_id); else await api.savePlan(dialog.plan.plan_id, planPayload({ ...dialog.plan, is_active: !dialog.plan.is_active })); updated("Plan updated."); }} /> : null}
  </section>;
}

function PlanForm({ plan, onClose, onSaved }) {
  const [initial] = useState(() => ({ name: plan?.name || "", code: plan?.code || "", description: plan?.description || "", ...pricingForm(plan), currency: plan?.currency || "INR", billing_cycle: plan?.billing_cycle || "monthly", max_users: plan?.max_users || 10, is_active: plan?.is_active ?? true }));
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const field = (name, value) => setForm({ ...form, [name]: value });
  async function save(event) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (!form.name.trim()) throw new Error("Plan name is required.");
      await api.savePlan(plan?.plan_id, planPayload({ ...form, ...pricingPayload(form) }));
      onSaved();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <Modal title={plan ? "Edit subscription plan" : "Create subscription plan"} onClose={onClose} dirty={JSON.stringify(initial) !== JSON.stringify(form)} busy={busy}>
    <form onSubmit={save}><fieldset className="fieldsetReset formColumns" disabled={busy}>
      <label>Plan name<input required maxLength={100} value={form.name} onChange={(e) => field("name", e.target.value)} /></label>
      <label>Plan code<input required pattern="[a-z0-9_-]{2,40}" title="2–40 lowercase letters, numbers, underscores or hyphens" value={form.code} onChange={(e) => field("code", e.target.value.toLowerCase().replace(/\s/g, "-"))} /></label>
      <label className="fullWidth">Description<textarea maxLength={2000} value={form.description} onChange={(e) => field("description", e.target.value)} /></label>
      <label>Currency<select value={form.currency} onChange={(e) => field("currency", e.target.value)}>{["INR", "USD", "EUR", "GBP"].map((c) => <option key={c}>{c}</option>)}</select></label>
      <label>Billing cycle<select value={form.billing_cycle} onChange={(e) => field("billing_cycle", e.target.value)}><option value="monthly">Monthly</option><option value="yearly">Yearly</option></select></label>
      <label>User limit<input required type="number" min="1" max="10000000" value={form.max_users} onChange={(e) => field("max_users", e.target.value)} /></label>
      <label>Status<select value={String(form.is_active)} onChange={(e) => field("is_active", e.target.value === "true")}><option value="true">Active</option><option value="false">Inactive</option></select></label>
      <PricingFields form={form} onChange={setForm} users={Number(form.max_users) || 0} currency={form.currency} estimate />
    </fieldset>
    <p className="muted">Organization totals use the number of registered employees. Existing organization pricing changes only when you update its subscription.</p>
    {error ? <Notice text={error} /> : null}
    <div className="modalFooter"><button className="secondaryButton" type="button" disabled={busy} data-close-modal>Cancel</button><button className="primaryButton" disabled={busy}>{busy ? "Saving…" : "Save plan"}</button></div></form>
  </Modal>;
}

export function AssignmentModal({ org, onClose, onSaved }) {
  const [selected, setSelected] = useState(org.subscription?.plan || null);
  const [pricing, setPricing] = useState(() => pricingForm(org.subscription?.plan));
  const [start, setStart] = useState(() => localDate(org.subscription?.starts_at || new Date()));
  const [end, setEnd] = useState(() => org.subscription?.ends_at ? localDate(org.subscription.ends_at) : "");
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  async function save(event) {
    event.preventDefault(); setBusy(true); setError("");
    try { await api.assignPlan(org.org_id, assignmentPayload(selected, pricingPayload(pricing), start, end)); onSaved(); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <Modal title={`Subscription pricing · ${org.org_name}`} onClose={onClose} dirty={dirty} busy={busy}>
    <PlanPicker selected={selected} disabled={busy} onSelect={(plan) => { setSelected(plan); setPricing(pricingForm(plan)); setDirty(true); }} />
    <form onSubmit={save}><fieldset className="fieldsetReset formColumns" disabled={busy}>
      <label>Starts on<input required type="date" value={start} onChange={(e) => { setStart(e.target.value); setDirty(true); }} /></label>
      <label>Ends on (optional)<input type="date" min={start} value={end} onChange={(e) => { setEnd(e.target.value); setDirty(true); }} /></label>
      {selected ? <PricingFields form={pricing} onChange={(value) => { setPricing(value); setDirty(true); }} users={org.users_count || 0} currency={selected.currency} /> : null}
    </fieldset><p className="muted">Prices can be customized for this organization. Employee limits are edited separately in organization settings.</p>
    {error ? <Notice text={error} /> : null}<div className="modalFooter"><button type="button" className="secondaryButton" disabled={busy} data-close-modal>Cancel</button><button className="primaryButton" disabled={busy || !selected}>{busy ? "Saving…" : "Save subscription"}</button></div></form>
  </Modal>;
}
