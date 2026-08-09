// Public download page for the Aaditech agent installer.
// Intentionally NOT behind login (like Login.jsx): fleet staff / GPO / Intune
// must be able to grab the package without a portal account. The installer
// carries no secrets — all server values are bal:Overridable and injected at
// INSTALL time (see agent-installer/README.md).
import { useEffect, useState } from "react";
import { agentInstallerApi } from "../api/client";

export default function DownloadAgent() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [buildState, setBuildState] = useState(null);
  const hasToken = Boolean(localStorage.getItem("aaditech_session_token"));

  useEffect(() => {
    agentInstallerApi
      .info()
      .then(setInfo)
      .catch((err) => setError(err.message));
  }, []);

  async function buildFromActions() {
    setBuildState({ busy: true, message: "Triggering GitHub Actions build…" });
    try {
      const res = await agentInstallerApi.build();
      setBuildState({ busy: false, message: res.message, ok: true });
      const fresh = await agentInstallerApi.info();
      setInfo(fresh);
    } catch (err) {
      const msg =
        err.response?.data?.message ||
        err.response?.data?.error ||
        "Build failed — check GITHUB_BUILD_PAT in infra/.env.";
      setBuildState({ busy: false, message: msg, ok: false });
    }
  }

  return (
    <div className="login-screen">
      <div className="login-card">
        <h1>Aaditech Agent Installer</h1>
        <p>
          One-click package for monitored Windows endpoints. Install runs
          silently; your server details are supplied automatically at deploy
          time — nothing here needs to be configured on the endpoint.
        </p>

        {error && <p className="error">Failed to check installer: {error}</p>}

        {hasToken && (
          <>
            <button
              className="sso-btn"
              style={{ width: "100%", marginTop: "0.5rem" }}
              onClick={buildFromActions}
              disabled={buildState?.busy}
            >
              {buildState?.busy ? "Building on GitHub Actions…" : "Build .exe from GitHub Actions"}
            </button>
            {buildState && (
              <p className={buildState.ok ? "hint" : "error"} style={{ marginTop: "0.5rem" }}>
                {buildState.message}
              </p>
            )}
          </>
        )}

        {info && !info.available && (
          <p className="error">
            {info.message ||
              "The installer has not been published yet. Ask an administrator to build and mount it."}
          </p>
        )}

        {info && info.available && (
          <>
            <a className="sso-btn" href="/api/agent-installer/download">
              Download Aaditech Agent ({info.size_mb} MB)
            </a>
            <p className="hint">
              Or, for mass rollout, point GPO / Intune at this URL:
            </p>
            <code className="url-hint">/api/agent-installer/download</code>
          </>
        )}
      </div>
    </div>
  );
}