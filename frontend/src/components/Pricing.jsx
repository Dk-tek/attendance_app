export function money(plan, amount = plan.price_minor || 0) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: plan.currency || "INR" }).format(amount / 100);
}

export function totalMinor(plan, users) {
  return (plan.price_minor || 0) + (plan.per_user_price_minor || 0) * users;
}

export function pricingForm(plan) {
  return { base_price: ((plan?.price_minor || 0) / 100).toFixed(2), per_user_price: ((plan?.per_user_price_minor || 0) / 100).toFixed(2) };
}

export function pricingPayload(form) {
  const values = [form.base_price, form.per_user_price].map((value) => Number(value));
  if ([form.base_price, form.per_user_price].some((value) => String(value).trim() === "") || values.some((value) => !Number.isFinite(value) || value < 0 || value > 100000000)) {
    throw new Error("Enter a valid base price and price per user between 0 and 100,000,000.");
  }
  return { price_minor: Math.round(values[0] * 100), per_user_price_minor: Math.round(values[1] * 100) };
}

export function PricingFields({ form, onChange, users, currency = "INR", disabled = false, estimate = false }) {
  const base = Number(form.base_price) || 0, perUser = Number(form.per_user_price) || 0;
  const plan = { currency, price_minor: Math.round(base * 100), per_user_price_minor: Math.round(perUser * 100) };
  return <>
    <label>Base price<input type="number" min="0" max="100000000" step="0.01" required disabled={disabled} value={form.base_price} onChange={(e) => onChange({ ...form, base_price: e.target.value })} /></label>
    <label>Price per user<input type="number" min="0" max="100000000" step="0.01" required disabled={disabled} value={form.per_user_price} onChange={(e) => onChange({ ...form, per_user_price: e.target.value })} /></label>
    <div className="priceSummary fullWidth" aria-live="polite"><span>{estimate ? "Total at user limit" : "Current total per billing cycle"}</span><strong>{money(plan, totalMinor(plan, users))}</strong><small>{money(plan)} base + {money(plan, plan.per_user_price_minor)} × {users} {estimate ? "users" : "registered employees"}</small></div>
  </>;
}
