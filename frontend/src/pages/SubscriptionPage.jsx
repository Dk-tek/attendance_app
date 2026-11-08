import { api } from "../api";
import { useLoad } from "../hooks/useLoad";
import { Loading, Notice } from "../components/Feedback";
import { Badge, dateLabel } from "../components/Listing";
import { money, totalMinor } from "../components/Pricing";

export function subscriptionStatus(subscription) {
  if (!subscription) return "Unassigned";
  if (new Date(subscription.starts_at) > new Date()) return "Scheduled";
  return subscription.ends_at && new Date(subscription.ends_at) < new Date() ? "Expired" : "Active";
}

export function SubscriptionPage() {
  const { data, loading, error } = useLoad(() => api.subscription(), []);
  if (loading) return <Loading />;
  if (error) return <Notice text={error} />;
  const sub = data.subscription, plan = sub?.plan;
  return <div className="splitPanels">
    <section className="panel detailPanel"><h2>{data.org_name}</h2><dl><dt>Organization code</dt><dd>{data.org_code}</dd><dt>Organization status</dt><dd><Badge active={data.is_active}>{data.is_active ? "Active" : "Inactive"}</Badge></dd><dt>Employee usage</dt><dd>{data.users_count} / {data.max_users}</dd></dl><progress aria-label="Employee capacity used" max={data.max_users || 1} value={data.users_count} /><p className="muted">Organization access and employee limits are managed by your Super Admin.</p></section>
    <section className="panel detailPanel"><h2>Assigned subscription</h2>{plan ? <>
      <dl><dt>Plan</dt><dd>{plan.name} ({plan.code})</dd><dt>Status</dt><dd>{subscriptionStatus(sub)}</dd><dt>Base price</dt><dd>{money(plan)}</dd><dt>Price per user</dt><dd>{money(plan, plan.per_user_price_minor || 0)}</dd><dt>Registered employees</dt><dd>{data.users_count}</dd><dt>Billing cycle</dt><dd>{plan.billing_cycle}</dd><dt>Starts</dt><dd>{dateLabel(sub.starts_at)}</dd><dt>Expires</dt><dd>{sub.ends_at ? dateLabel(sub.ends_at) : "No expiry set"}</dd></dl>
      <div className="priceSummary"><span>Current total per billing cycle</span><strong>{money(plan, totalMinor(plan, data.users_count))}</strong><small>{money(plan)} base + {money(plan, plan.per_user_price_minor || 0)} × {data.users_count} registered employees</small></div>
      <p className="muted">The total updates with your registered employee count, including inactive accounts. Contact your Super Admin to change your plan or agreed pricing.</p>
    </> : <div className="emptyState"><strong>No subscription assigned</strong><p>Contact your Super Admin to assign a plan.</p></div>}</section>
  </div>;
}
