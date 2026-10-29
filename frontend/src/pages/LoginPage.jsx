import { useState } from "react";
import { Moon, Sun } from "lucide-react";
import { api } from "../api";

export function LoginPage({ onLogin, theme, setTheme }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const session = await api.login({ username, password });
      onLogin(session);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="loginPage">
      <section className="loginIntro">
        <p className="eyebrow">Attendance monitoring application</p>
        <h1>TrackPulse</h1>
        <p>
          A real-time attendance tracking application for face-based check-ins,
          organization monitoring, employee movement history, and efficient location visibility.
        </p>
      </section>
      <form className="loginPanel" onSubmit={submit}>
        <div className="loginPanelHead">
          <div>
            <p className="eyebrow">Secure access</p>
            <h2>Sign in</h2>
          </div>
          <button className="iconButton" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} title="Toggle theme">
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
        <label>
          Email or employee ID
          <input value={username} onChange={(event) => setUsername(event.target.value)} required />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </label>
        {error ? <div className="notice error">{error}</div> : null}
        <button className="primaryButton" type="submit" disabled={loading}>
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}
