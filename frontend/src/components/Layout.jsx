import { useState } from "react";
import { Brand } from "./Brand";
import {
  Activity,
  BarChart3,
  Building2,
  ListChecks,
  LogOut,
  MapPinned,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  ShieldCheck,
  Sun,
  Users
} from "lucide-react";

const navByRole = {
  superadmin: [
    { id: "overview", label: "Overview", icon: BarChart3 },
    { id: "organizations", label: "Organizations", icon: Building2 },
    { id: "plans", label: "Subscription plans", icon: ListChecks },
    { id: "insights", label: "Insights", icon: Activity },
    { id: "terms", label: "Terms & Conditions", icon: ShieldCheck },
    { id: "privacy", label: "Privacy Policy", icon: ShieldCheck }
  ],
  org_admin: [
    { id: "overview", label: "Overview", icon: BarChart3 },
    { id: "users", label: "Users", icon: Users },
    { id: "attendance", label: "Attendance", icon: MapPinned },
    { id: "organization", label: "Organization", icon: Building2 },
    { id: "subscription", label: "Subscription", icon: ListChecks },
    { id: "terms", label: "Terms & Conditions", icon: ShieldCheck },
    { id: "privacy", label: "Privacy Policy", icon: ShieldCheck },
    { id: "settings", label: "Settings", icon: Settings }
  ],
  user: [
    { id: "overview", label: "Overview", icon: BarChart3 },
    { id: "records", label: "Records", icon: ListChecks },
    { id: "map", label: "Map", icon: MapPinned },
    { id: "terms", label: "Terms & Conditions", icon: ShieldCheck },
    { id: "privacy", label: "Privacy Policy", icon: ShieldCheck }
  ]
};

export function Layout({ session, theme, setTheme, activePage, setActivePage, onLogout, children }) {
  const nav = navByRole[session.role] || [];
  const [collapsed, setCollapsed] = useState(false);
  const [logoutError, setLogoutError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const current = nav.find((item) => item.id === activePage);

  return (
    <div className={`appShell ${collapsed ? "navCollapsed" : ""}`}>
      <a href="#workspace" className="skipLink" onClick={(event) => { event.preventDefault(); document.getElementById("main-content")?.focus(); }}>Skip to content</a>
      <aside className="sidebar">
        <div className="brand">
          <Brand compact />
          <div>
            <strong>Field Pixel</strong>
            <span>{session.role?.replace("_", " ")}</span>
          </div>
        </div>
        <button className="collapseButton iconButton" type="button" aria-label={collapsed ? "Expand navigation" : "Collapse navigation"} title={collapsed ? "Expand navigation" : "Collapse navigation"} aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}>{collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}</button>
        <nav aria-label="Dashboard navigation">
          {nav.map((item) => (
            <button
              key={item.id}
              className={activePage === item.id ? "navButton active" : "navButton"}
              type="button"
              aria-current={activePage === item.id ? "page" : undefined}
              title={item.label}
              onClick={() => setActivePage(item.id)}
            >
              <item.icon size={17} />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebarFooter"><span className="avatar">{titleFor(session).slice(0, 1).toUpperCase()}</span><div><strong>{titleFor(session)}</strong><small>{session.admin_email || session.user_email || session.email}</small></div></div>
      </aside>
      <main className="workspace" id="main-content" tabIndex={-1}>
        <header className="workspaceTop">
          <div>
            <p className="eyebrow">Field Pixel / {session.role === "superadmin" ? "Administration" : "Workspace"}</p>
            <h1>{current?.label || "Overview"}</h1>
            <p className="headerCopy">
              {descriptions[activePage] || "Manage your workforce and attendance operations."}
            </p>
          </div>
          <div className="toolbar">
            <span className="workspaceIdentity">{titleFor(session)}</span>
            <button className="iconButton" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} title="Toggle theme" aria-label="Toggle theme">
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button className="iconButton" type="button" disabled={loggingOut} onClick={async () => { setLoggingOut(true); try { await onLogout(); } catch (err) { setLogoutError(err.message); } finally { setLoggingOut(false); } }} title="Logout" aria-label="Logout">
              <LogOut size={18} />
            </button>
          </div>
        </header>
        {logoutError ? <div className="notice error" role="alert">{logoutError}</div> : null}
        {children}
      </main>
    </div>
  );
}

const descriptions = {
  overview: "A live view of attendance, enrollment and workforce capacity.",
  users: "Manage employee access and face enrollment in your organization.",
  organizations: "Manage organizations, administrators and workforce limits.",
  attendance: "Explore attendance records and employee location history.",
  settings: "Review organization tracking and automatic checkout rules.",
  plans: "Configure base pricing, per-user pricing and subscription limits.",
  subscription: "Review your assigned subscription and workforce usage.",
  organization: "Your organization details and workforce allocation.",
  terms: "Terms governing the use of your organization's services.",
  privacy: "How your organization handles personal information.",
  records: "Search your attendance history by date.",
  map: "Explore your recorded attendance and tracking locations.",
  insights: "Compare enrollment and attendance across organizations."
};

function titleFor(session) {
  if (session.role === "superadmin") return "Global attendance control";
  if (session.role === "org_admin") return session.admin_name || "Organization operations";
  if (session.role === "user") return session.employee_name || "My attendance tracking";
  return "Field Pixel";
}
