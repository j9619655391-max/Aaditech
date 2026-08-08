// Sign in with either your Microsoft 365 account (Azure AD SSO) OR the local
// admin account created by the one-click setup wizard (username + password).
// Both paths return the same portal JWT, stored and used for every /api/* call.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

export default function Login() {
  const navigate = useNavigate();
  const [error, setError] = useState(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    if (token) {
      localStorage.setItem("aaditech_session_token", token);
      navigate("/", { replace: true });
    }
  }, [navigate]);

  function startSsoLogin() {
    window.location.href = "/api/auth/sso/login";
  }

  async function localLogin(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const resp = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Login failed");
      localStorage.setItem("aaditech_session_token", data.access_token);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <h1>Aaditech IT Monitoring & Automation Platform</h1>

        <form onSubmit={localLogin} className="local-login">
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
          {error && <p className="error">{error}</p>}
          <button type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="login-divider">
          <span>or</span>
        </div>

        <button onClick={startSsoLogin} className="sso-btn">
          Sign in with Microsoft 365
        </button>
      </div>
    </div>
  );
}
