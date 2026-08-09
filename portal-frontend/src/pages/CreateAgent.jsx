// "Create Agent" tab — one place to build/publish the agent installer and
// hand out the one-click package. OS-aware:
//   - Windows admin machine  -> build the .exe locally (build-agent-installer.ps1)
//                              and upload it here, OR use GitHub Actions.
//   - Ubuntu/Linux portal    -> build via GitHub Actions and pull it here.
// Secrets (enrollment key, mesh ID) are fetched over HTTPS from the protected
// config endpoint and only embedded into AgentConfig.json on the admin's
// machine — never shipped in plaintext by the server.
import { useEffect, useState } from "react";
import { agentInstallerApi } from "../api/client";

const IS_WINDOWS = /Windows|Win64|Win32/i.test(navigator.userAgent);

export default function CreateAgent() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [buildState, setBuildState] = useState(null);
  const [uploadState, setUploadState] = useState(null);
  const [config, setConfig] = useState(null);
  const [endpointId, setEndpointId] = useState("");
  const [token, setToken] = useState(null);

  useEffect(() => {
    agentInstallerApi
      .info()
      .then(setInfo)
      .catch((err) => setError(err.message));
    agentInstallerApi
      .config()
      .then(setConfig)
      .catch(() => setConfig(null));
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

  async function uploadLocalExe(evt) {
    setUploadState({ busy: true, message: "Uploading locally-built installer…" });
    try {
      const res = await agentInstallerApi.upload(evt.target.files[0]);
      setUploadState({ busy: false, message: res.message, ok: true });
      const fresh = await agentInstallerApi.info();
      setInfo(fresh);
    } catch (err) {
      const msg =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        "Upload failed.";
      setUploadState({ busy: false, message: msg, ok: false });
    }
  }

  async function mintToken() {
    const id = endpointId.trim() || (config ? config.managerIp + "-" + Date.now() : "endpoint-1");
    try {
      const res = await agentInstallerApi.mintToken(id);
      setToken(res);
    } catch (err) {
      const msg = err.response?.data?.detail || "Token mint failed.";
      setToken({ error: msg });
    }
  }

  const managerIp = config?.managerIp || "";

  return (
    <div className="page">
      <h1>Create Agent</h1>
      <p className="hint">
        Build the Aaditech agent installer and hand out the one-click endpoint
        package. Detected platform:{" "}
        <b>{IS_WINDOWS ? "Windows — build locally" : "Linux/Ubuntu — build via GitHub"}</b>.
      </p>

      {error && <p className="error">Failed to check installer: {error}</p>}

      <section style={{ marginTop: "1.5rem" }}>
        <h2>1. Build the installer</h2>
        {IS_WINDOWS ? (
          <>
            <p className="hint">
              On this Windows machine, run <b>agent-installer/build-agent-installer.ps1</b>{" "}
              from the repo (it downloads WiX + the vendor agents and compiles
              Aaditech-Agent-Setup.exe). Then upload the result below:
            </p>
            <input
              type="file"
              accept=".exe"
              onChange={uploadLocalExe}
              style={{ marginTop: "0.5rem" }}
            />
            {uploadState && (
              <p className={uploadState.ok ? "hint" : "error"}>{uploadState.message}</p>
            )}
            <p className="hint">
              Or trigger a GitHub Actions build from here instead:
            </p>
            <button className="sso-btn" onClick={buildFromActions} disabled={buildState?.busy}>
              {buildState?.busy ? "Building on GitHub Actions…" : "Build via GitHub Actions"}
            </button>
          </>
        ) : (
          <>
            <p className="hint">
              This portal runs on Linux, so the .exe is built by GitHub Actions
              and pulled here automatically (requires GITHUB_BUILD_PAT from
              setup):
            </p>
            <button className="sso-btn" onClick={buildFromActions} disabled={buildState?.busy}>
              {buildState?.busy ? "Building on GitHub Actions…" : "Build .exe from GitHub Actions"}
            </button>
          </>
        )}
        {buildState && (
          <p className={buildState.ok ? "hint" : "error"} style={{ marginTop: "0.5rem" }}>
            {buildState.message}
          </p>
        )}
      </section>

      <section style={{ marginTop: "1.5rem" }}>
        <h2>2. Download the one-click package</h2>
        <p className="hint">
          Server values come from the portal config — nothing to type on the
          endpoint. On the endpoint: unzip, then double-click{" "}
          <b>install-agent.bat</b>.
        </p>
        <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          {info && info.available && (
            <a className="sso-btn" href={agentInstallerApi.downloadUrl()}>
              Aaditech-Agent-Setup.exe ({info.size_mb} MB)
            </a>
          )}
          <a className="sso-btn" href={agentInstallerApi.configUrl()}>
            AgentConfig.json
          </a>
          <a className="sso-btn" href={agentInstallerApi.rootCaUrl()}>
            Root CA (rootCA.pem)
          </a>
        </div>
        {info && !info.available && (
          <p className="error">
            Installer not published yet — build it in step 1 first.
          </p>
        )}
      </section>

      <section style={{ marginTop: "1.5rem" }}>
        <h2>3. Endpoint poller token (optional)</h2>
        <p className="hint">
          Mint a per-endpoint service token for{" "}
          <b>self-healing/agent-command-poller.ps1</b> (Category B commands).
          Paste it into AADITECH_ENV.txt on the endpoint.
        </p>
        <input
          value={endpointId}
          onChange={(e) => setEndpointId(e.target.value)}
          placeholder="Endpoint ID (default: auto)"
          style={{ marginTop: "0.5rem", padding: "0.4rem" }}
        />
        <button className="sso-btn" onClick={mintToken} style={{ marginLeft: "0.5rem" }}>
          Mint token
        </button>
        {token && (
          <pre
            className="url-hint"
            style={{ marginTop: "0.75rem", whiteSpace: "pre-wrap", background: "#0b1220", padding: "0.75rem", borderRadius: 6 }}
          >
            {token.error ? `Error: ${token.error}` : `Endpoint: ${token.endpoint_id}\nToken: ${token.token}\nExpiry: ${token.expiry_days} days`}
          </pre>
        )}
      </section>

      {managerIp && (
        <section style={{ marginTop: "1.5rem" }}>
          <h2>Deployment summary</h2>
          <pre className="url-hint" style={{ background: "#0b1220", padding: "0.75rem", borderRadius: 6 }}>
{`Manager IP   : ${config?.managerIp || "?"}
Zabbix IP    : ${config?.zabbixServerIp || "?"}
Mesh URL     : ${config?.meshCentralUrl || "?"}
Enroll key   : [configured — see AgentConfig.json]
Mesh ID      : ${config?.meshId || "(empty — set after creating a MeshCentral device group)"}`}
          </pre>
        </section>
      )}
    </div>
  );
}
