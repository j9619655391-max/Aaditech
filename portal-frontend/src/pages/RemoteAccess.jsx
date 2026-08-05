import { useState } from "react";
import { remoteApi } from "../api/client";

export default function RemoteAccess() {
  const [deviceId, setDeviceId] = useState("");
  const [session, setSession] = useState(null);
  const [error, setError] = useState(null);
  const [connecting, setConnecting] = useState(false);

  async function connect() {
    setConnecting(true);
    setError(null);
    try {
      const result = await remoteApi.startSession(deviceId);
      setSession(result);
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message);
    } finally {
      setConnecting(false);
    }
  }

  async function disconnect() {
    if (session?.sessionId) {
      await remoteApi.endSession(session.sessionId);
    }
    setSession(null);
  }

  return (
    <div className="page remote-page">
      <h2>Remote Access</h2>
      <div className="remote-controls">
        <input
          placeholder="Device ID"
          value={deviceId}
          onChange={(e) => setDeviceId(e.target.value)}
        />
        <button onClick={connect} disabled={!deviceId || connecting}>
          {connecting ? "Connecting…" : "Connect"}
        </button>
        {session && <button onClick={disconnect}>Disconnect</button>}
      </div>

      {error && <p className="error">{error}</p>}

      {session && (
        <div className="remote-session-frame">
          {/* Embedded session — end user never sees the MeshCentral host URL directly */}
          <iframe title="remote-session" src={session.sessionUrl} width="100%" height="600" frameBorder="0" />
        </div>
      )}
    </div>
  );
}
