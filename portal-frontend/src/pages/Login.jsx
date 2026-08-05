// Production note: this redirects to the Azure AD SSO flow. The backend
// exchanges the SSO callback for a portal-scoped JWT (see app/auth.py)
// and redirects back here with the token, which we store and use for
// every subsequent /api/* call.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

export default function Login() {
  const navigate = useNavigate();
  const [error, setError] = useState(null);

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

  return (
    <div className="login-screen">
      <div className="login-card">
        <h1>Aaditech IT Monitoring & Automation Platform</h1>
        <p>Sign in with your organization account to continue.</p>
        {error && <p className="error">{error}</p>}
        <button onClick={startSsoLogin} className="sso-btn">
          Sign in with Microsoft 365
        </button>
      </div>
    </div>
  );
}
