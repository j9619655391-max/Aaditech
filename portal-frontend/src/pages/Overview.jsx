import { useEffect, useState } from "react";
import { dashboardsApi, alertsApi } from "../api/client";

export default function Overview() {
  const [infraEmbed, setInfraEmbed] = useState(null);
  const [securityEmbed, setSecurityEmbed] = useState(null);
  const [agentHealth, setAgentHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    Promise.all([
      dashboardsApi.embedUrl("infra-overview"),
      dashboardsApi.embedUrl("security-overview"),
      alertsApi.agentHealth(),
    ])
      .then(([infra, security, health]) => {
        setInfraEmbed(infra);
        setSecurityEmbed(security);
        setAgentHealth(health);
      })
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error">Failed to load overview: {error}</p>;

  return (
    <div className="page overview-page">
      <h2>Overview</h2>

      <section className="agent-health-card">
        <h3>Fleet Agent Health</h3>
        {agentHealth ? (
          <ul>
            {Object.entries(agentHealth).map(([status, count]) => (
              <li key={status}>
                {status}: {count}
              </li>
            ))}
          </ul>
        ) : (
          <p>Loading…</p>
        )}
      </section>

      <section className="dashboard-embed">
        <h3>Infrastructure Performance</h3>
        {infraEmbed && (
          <iframe
            title="infra-overview"
            src={infraEmbed.embed_url}
            width="100%"
            height="400"
            frameBorder="0"
          />
        )}
      </section>

      <section className="dashboard-embed">
        <h3>Security Overview</h3>
        {securityEmbed && (
          <iframe
            title="security-overview"
            src={securityEmbed.embed_url}
            width="100%"
            height="400"
            frameBorder="0"
          />
        )}
      </section>
    </div>
  );
}
