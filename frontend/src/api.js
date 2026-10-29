const API_BASE = import.meta.env.VITE_API_BASE || "";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  const type = response.headers.get("content-type") || "";
  const body = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = body?.detail || body?.message || "Request failed";
    throw new Error(message);
  }
  return body;
}

export const api = {
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
