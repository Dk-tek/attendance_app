import { useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks/useLoad";
import { Loading, Notice } from "./Feedback";
import { initialQuery } from "./Listing";
import { PaginationControls } from "./PaginationControls";
import { money } from "./Pricing";

export function PlanPicker({ selected, onSelect, disabled = false }) {
  const [query, setQuery] = useState({ ...initialQuery, status: "active", sort: "name", direction: "asc" });
  const { data, loading, error } = useLoad(() => api.plans(query), [JSON.stringify(query)]);
  return <div className="planPicker fullWidth"><label>Find subscription plan<input disabled={disabled} type="search" value={query.q} onChange={(e) => setQuery({ ...query, q: e.target.value, page: 1 })} /></label>
    {selected ? <p className="muted">Selected: <strong>{selected.name}</strong> ({selected.code})</p> : null}
    {error ? <Notice text={error} /> : null}
    {loading ? <Loading /> : data ? <><div className="formGrid">{data.items.length ? data.items.map((plan) => <label className="checkRow" key={plan.plan_id}><input type="radio" name="subscription-plan" disabled={disabled} checked={selected?.plan_id === plan.plan_id} onChange={() => onSelect(plan)} /><span>{plan.name} · {money(plan)} base + {money(plan, plan.per_user_price_minor || 0)} / user · {plan.billing_cycle}</span></label>) : <p className="muted">No active plans match. Create or activate a plan first.</p>}</div><PaginationControls pagination={data.pagination} onPageChange={(page) => setQuery({ ...query, page })} /></> : null}
  </div>;
}

export function assignmentPayload(plan, pricing, start, end) {
  return { plan_id: plan.plan_id, ...pricing, starts_at: `${start}T00:00:00+05:30`, ends_at: end ? `${end}T23:59:59+05:30` : null };
}

export function localDate(value = new Date()) {
  return new Date(value).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}
