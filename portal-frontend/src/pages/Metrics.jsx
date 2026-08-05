import { useEffect, useState } from "react";
import { metricsApi } from "../api/client";

export default function Metrics() {
  const [hosts, setHosts] = useState([]);
  const [triggers, setTriggers] = useState([]);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([metricsApi.hosts(), metricsApi.triggers(2)])
      .then(([h, t]) => {
        setHosts(h);
        setTriggers(t);
      })
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">Failed to load metrics: {error}</p>;

  return (
    <div className="page metrics-page">
      <h2>Infrastructure Metrics</h2>

      <section>
        <h3>Hosts ({hosts.length})</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>Host</th>
              <th>Status</th>
              <th>Available</th>
            </tr>
          </thead>
          <tbody>
            {hosts.map((h) => (
              <tr key={h.hostid}>
                <td>{h.host}</td>
                <td>{h.status === "0" ? "Monitored" : "Not monitored"}</td>
                <td>{h.available === "1" ? "Available" : "Unavailable"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3>Active Triggers ({triggers.length})</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>Description</th>
              <th>Severity</th>
              <th>Last Changed</th>
            </tr>
          </thead>
          <tbody>
            {triggers.map((t) => (
              <tr key={t.triggerid}>
                <td>{t.description}</td>
                <td>{t.priority}</td>
                <td>{new Date(Number(t.lastchange) * 1000).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
