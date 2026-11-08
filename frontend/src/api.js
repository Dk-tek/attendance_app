const API_BASE = import.meta.env.VITE_API_BASE || "";

async function request(path, options = {}) {
  let response;
  try { response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    signal: AbortSignal.timeout(20000),
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  }); } catch { throw new Error("Unable to connect. Check your connection and try again."); }

  const type = response.headers.get("content-type") || "";
  const body = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    if (response.status === 401 && !path.includes("/auth/login")) window.dispatchEvent(new Event("session-expired"));
    const detail = body?.detail || body?.message;
    const fields = { price_minor: "Base price", per_user_price_minor: "Price per user", max_users: "User limit", code: "Plan code", name: "Plan name", currency: "Currency", billing_cycle: "Billing cycle" };
    const validation = Array.isArray(detail) ? detail.map((issue) => {
      const field = issue.loc?.at(-1);
      const label = fields[field] || String(field || "Form field").replaceAll("_", " ");
      const reason = issue.type === "missing" ? "is required" : issue.type === "string_pattern_mismatch" ? "must use 2–40 lowercase letters, numbers, underscores or hyphens" : "has an invalid value";
      return `${label} ${reason}.`;
    }).join(" ") : "";
    const message = response.status >= 500 ? "The server could not complete this request. Please try again." : Array.isArray(detail) ? validation : typeof detail === "string" ? detail : "Request failed. Please try again.";
    const error = new Error(message); error.status = response.status; throw error;
  }
  return body;
}

export const api = {
  listUsers: (params) => request(`/api/org-admin/users?${new URLSearchParams(params)}`),
  updateUser: (id, payload) => request(`/api/org-admin/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  listOrganizations: (params) => request(`/api/superadmin/organizations?${new URLSearchParams(params)}`),
  policy: (kind) => request(`/api/superadmin/policies/${kind}`),
  savePolicy: (kind, payload) => request(`/api/superadmin/policies/${kind}`, { method: "PUT", body: JSON.stringify(payload) }),
  publishedPolicy: (kind) => request(`/api/policies/${kind}`),
  plans: (params) => request(`/api/superadmin/plans?${new URLSearchParams(params)}`),
  savePlan: (id, payload) => request(`/api/superadmin/plans${id ? `/${id}` : ""}`, { method: id ? "PUT" : "POST", body: JSON.stringify(payload) }),
  deletePlan: (id) => request(`/api/superadmin/plans/${id}`, { method: "DELETE" }),
  assignPlan: (id, payload) => request(`/api/superadmin/orgs/${id}/subscription`, { method: "PUT", body: JSON.stringify(payload) }),
  subscription: () => request("/api/org-admin/subscription"),
  session: () => request("/api/auth/session"),
  login: (payload) => request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  superadminDashboard: (params = {}) => request(`/api/superadmin/dashboard?${new URLSearchParams(params)}`),
  superadminOrg: (orgId, params = {}) => request(`/api/superadmin/orgs/${orgId}?${new URLSearchParams(params)}`),
  createOrg: (payload) => request("/api/superadmin/orgs", {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  updateOrg: (orgId, payload) => request(`/api/superadmin/orgs/${orgId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  }),
  toggleOrg: (orgId) => request(`/api/superadmin/orgs/${orgId}/toggle`, { method: "POST" }),
  orgDashboard: (params = {}) => request(`/api/org-admin/dashboard?${new URLSearchParams(params)}`),
  createUser: (payload) => request("/api/org-admin/users", {
    method: "POST",
    body: JSON.stringify(payload)
  }),
  toggleUser: (userId) => request(`/api/org-admin/users/${userId}/toggle`, { method: "POST" }),
  orgAttendance: (params) => request(`/api/org-admin/attendance?${new URLSearchParams(params)}`),
  userDashboard: (params) => request(`/api/user/dashboard?${new URLSearchParams(params)}`)
};
