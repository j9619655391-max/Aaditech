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

  useEffect(() => {
    agentInstallerApi
      .info()
      .then(setInfo)
      .catch((err) => setError(err.message));
  }, []);

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