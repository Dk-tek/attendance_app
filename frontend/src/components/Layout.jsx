import {
  Activity,
  BarChart3,
  Building2,
  ListChecks,
  LogOut,
  MapPinned,
  Moon,
  Settings,
  ShieldCheck,
  Sun,
  Users
} from "lucide-react";

const navByRole = {
  superadmin: [
    { id: "overview", label: "Overview", icon: BarChart3 },
    { id: "organizations", label: "Organizations", icon: Building2 },
    { id: "insights", label: "Insights", icon: Activity }
  ],
  org_admin: [
    { id: "overview", label: "Overview", icon: BarChart3 },
    { id: "users", label: "Users", icon: Users },
    { id: "attendance", label: "Attendance", icon: MapPinned },
    { id: "settings", label: "Settings", icon: Settings }
  ],
  user: [
    { id: "overview", label: "Overview", icon: BarChart3 },
    { id: "records", label: "Records", icon: ListChecks },
    { id: "map", label: "Map", icon: MapPinned }
  ]
};

export function Layout({ session, theme, setTheme, activePage, setActivePage, onLogout, children }) {
  const nav = navByRole[session.role] || [];

  return (
    <div className="appShell">
      <aside className="sidebar">
        <div className="brand">
          <ShieldCheck size={24} />
          <div>
            <strong>TrackPulse</strong>
            <span>{session.role?.replace("_", " ")}</span>
          </div>
        </div>
        <nav aria-label="Dashboard navigation">
          {nav.map((item) => (
            <button
              key={item.id}
              className={activePage === item.id ? "navButton active" : "navButton"}
              type="button"
              onClick={() => setActivePage(item.id)}
            >
              <item.icon size={17} />
              {item.label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="workspace">
        <header className="workspaceTop">
          <div>
            <p className="eyebrow">Attendance monitoring application</p>
            <h1>{titleFor(session)}</h1>
            <p className="headerCopy">
              Efficient face attendance, workforce movement history, and real-time tracking for operational teams.
            </p>
          </div>
          <div className="toolbar">
            <button className="iconButton" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} title="Toggle theme">
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button className="iconButton" type="button" onClick={onLogout} title="Logout">
              <LogOut size={18} />
            </button>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}

function titleFor(session) {
  if (session.role === "superadmin") return "Global attendance control";
  if (session.role === "org_admin") return session.admin_name || "Organization operations";
  if (session.role === "user") return session.employee_name || "My attendance tracking";
  return "TrackPulse";
}
