import { lazy, Suspense, useEffect, useState } from "react";
import { api } from "./api";
import { Layout } from "./components/Layout";
import { Loading } from "./components/Feedback";
import { usePageSeo } from "./hooks/usePageSeo";

const LoginPage = lazy(() => import("./pages/LoginPage").then((module) => ({ default: module.LoginPage })));
const OrgAdminPage = lazy(() => import("./pages/OrgAdminPage").then((module) => ({ default: module.OrgAdminPage })));
const SuperadminPage = lazy(() => import("./pages/SuperadminPage").then((module) => ({ default: module.SuperadminPage })));
const UserPage = lazy(() => import("./pages/UserPage").then((module) => ({ default: module.UserPage })));
const LandingPage = lazy(() => import("./pages/LandingPage").then((module) => ({ default: module.LandingPage })));

export default function App() {
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");
  const [activePage, setActivePage] = useState("overview");
  const [session, setSession] = useState(null);
  const [booting, setBooting] = useState(true);
  const [route, setRoute] = useState(window.location.hash);
  usePageSeo(route, session?.role, activePage);

  useEffect(() => {
    const navigate = () => setRoute(window.location.hash);
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => {
    setActivePage("overview");
  }, [session?.role]);

  useEffect(() => {
    const expire = () => { setSession(null); window.location.hash = "login"; };
    window.addEventListener("session-expired", expire);
    api.session()
      .then((value) => setSession(value.authenticated ? value : null))
      .catch(() => setSession(null))
      .finally(() => setBooting(false));
    return () => window.removeEventListener("session-expired", expire);
  }, []);

  async function logout() {
    await api.logout();
    setSession(null);
    setActivePage("overview");
    window.location.hash = "home";
  }

  if (booting) return <Loading />;
  if (!["#login", "#workspace"].includes(route)) return <Suspense fallback={<Loading />}><LandingPage signedIn={!!session} onAccess={() => { window.location.hash = session ? "workspace" : "login"; }} /></Suspense>;
  if (!session) {
    return (
      <Suspense fallback={<Loading />}>
        <LoginPage onBack={() => { window.location.hash = "home"; }} onLogin={(value) => { setSession(value); window.location.hash = "workspace"; }} theme={theme} setTheme={setTheme} />
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
