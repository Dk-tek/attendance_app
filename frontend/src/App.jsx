import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "./api";
import { Layout } from "./components/Layout";
import { Loading } from "./components/Feedback";

const LoginPage = lazy(() => import("./pages/LoginPage").then((module) => ({ default: module.LoginPage })));
const OrgAdminPage = lazy(() => import("./pages/OrgAdminPage").then((module) => ({ default: module.OrgAdminPage })));
const SuperadminPage = lazy(() => import("./pages/SuperadminPage").then((module) => ({ default: module.SuperadminPage })));
const UserPage = lazy(() => import("./pages/UserPage").then((module) => ({ default: module.UserPage })));

export default function App() {
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");
  const [activePage, setActivePage] = useState("overview");
  const [session, setSession] = useState(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    setActivePage("overview");
  }, [session?.role]);

  useEffect(() => {
    api.session()
      .then((value) => setSession(value.authenticated ? value : null))
      .finally(() => setBooting(false));
  }, []);

  async function logout() {
    await api.logout();
    setSession(null);
    setActivePage("overview");
  }

  if (booting) return <Loading />;
  if (!session) {
    return (
      <Suspense fallback={<Loading />}>
        <LoginPage onLogin={setSession} theme={theme} setTheme={setTheme} />
      </Suspense>
    );
  }

  return (
    <Layout
      session={session}
      theme={theme}
      setTheme={setTheme}
      activePage={activePage}
      setActivePage={setActivePage}
      onLogout={logout}
    >
      <Suspense fallback={<Loading />}>
        {session.role === "superadmin" ? <SuperadminPage activePage={activePage} setActivePage={setActivePage} /> : null}
        {session.role === "org_admin" ? <OrgAdminPage activePage={activePage} /> : null}
        {session.role === "user" ? <UserPage activePage={activePage} /> : null}
      </Suspense>
    </Layout>
  );
}
