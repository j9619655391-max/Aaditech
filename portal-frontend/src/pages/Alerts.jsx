import { useEffect, useState } from "react";
import { alertsApi } from "../api/client";

const TABS = ["alerts", "fim", "vulnerabilities"];

export default function Alerts() {
  const [tab, setTab] = useState("alerts");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const fetcher =
      tab === "alerts" ? alertsApi.list : tab === "fim" ? alertsApi.fim : alertsApi.vulnerabilities;

    fetcher({ limit: 50 })
      .then(setItems)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [tab]);

  return (
    <div className="page alerts-page">
      <h2>Security Alerts</h2>
      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t}
            className={t === tab ? "tab active" : "tab"}
            onClick={() => setTab(t)}
          >
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      {loading && <p>Loading…</p>}
      {error && <p className="error">{error}</p>}

      {!loading && !error && (
        <table className="data-table">
          <tbody>
            {items.length === 0 && (
              <tr>
                <td>No items found.</td>
              </tr>
            )}
            {items.map((item, idx) => (
              <tr key={idx}>
                <td>
                  <pre>{JSON.stringify(item, null, 2)}</pre>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
