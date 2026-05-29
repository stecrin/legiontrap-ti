// ui/dashboard/src/pages/Login.jsx
// -----------------------------------------------------------------------------
// LegionTrap TI – Login Screen
//
// • Full-screen centered card
// • Uses the tactical CSS utilities from index.css (lt-* classes)
// • Calls FastAPI /api/login and stores JWT in localStorage
// • onLogin() is passed from App.jsx and flips the app into dashboard mode
// -----------------------------------------------------------------------------

import { useState } from "react";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("username", username);
      formData.append("password", password);

      const res = await fetch("/api/login", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Invalid credentials");
      }

      const data = await res.json();
      localStorage.setItem("token", data.access_token);
      onLogin();
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="lt-fullscreen-center">
      <div className="lt-page">
        <div className="lt-card">
          <div style={{ position: "relative", zIndex: 1 }}>
            {/* Heading block -------------------------------------------------- */}
            <div className="lt-heading-sub">ACCESS CONTROL</div>
            <h1 className="lt-heading-xl">LegionTrap TI Login</h1>
            <p
              className="lt-text-muted"
              style={{ maxWidth: 520, marginBottom: "1.25rem" }}
            >
              Secure threat-intel console – authorised operators only. All
              access is monitored and logged.
            </p>

            {/* FULL-WIDTH FORM PANEL ------------------------------------------ */}
            <form
              onSubmit={handleSubmit}
              className="lt-panel lt-panel-wide"
            >
              <label className="lt-field-label" htmlFor="username">
                Username
              </label>
              <input
                id="username"
                type="text"
                className="lt-input"
                placeholder="operator@legion"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />

              <div style={{ height: 14 }} />

              <label className="lt-field-label" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                className="lt-input"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />

              {error && (
                <p
                  style={{
                    marginTop: 10,
                    color: "var(--lt-danger)",
                    fontSize: "0.85rem",
                  }}
                >
                  {error}
                </p>
              )}

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginTop: 18,
                }}
              >
                <button
                  type="submit"
                  disabled={loading}
                  className="lt-btn-primary"
                >
                  {loading ? "Authorising…" : "Login"}
                </button>

                <span className="lt-text-muted">
                  Tip: press Enter to submit.
                </span>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
