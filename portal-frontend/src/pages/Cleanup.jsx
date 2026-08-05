// Category B — Approval-Required Cleanup UI (spec §3.5).
// Renders scan reports as a checklist (all items selected by default per
// the spec's step 3), lets the engineer uncheck items to preserve, and
// only calls the approve API for whatever remains checked. Requires the
// Cleanup Approver role — a plain SSO login is not enough (§7.1, closes R-8).
// The backend enforces this too; this page just reflects that in the UI
// (disabling Approve for non-approvers) so it's not a confusing dead end.
import { useEffect, useState } from "react";
import { cleanupApi } from "../api/client";

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

function ReportCard({ report, onApproved }) {
  const [checked, setChecked] = useState(
    () => new Set(report.items.filter((i) => i.status === "pending_approval").map((i) => i.item_id))
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  function toggle(itemId) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  }

  async function handleApprove() {
    setBusy(true);
    setError(null);
    try {
      await cleanupApi.approve(report.report_id, Array.from(checked));
      onApproved();
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message);
    } finally {
      setBusy(false);
    }
  }

  const pendingItems = report.items.filter((i) => i.status === "pending_approval");
  if (pendingItems.length === 0) return null;

  return (
    <div className="cleanup-report-card">
      <h3>
        {report.endpoint_name}{" "}
        <span className={`trigger-badge ${report.triggered_by}`}>
          {report.triggered_by === "low_disk_space" ? "Low Disk Space — Emergency Hold (24h)" : "Scheduled — Standard Hold (7d)"}
        </span>
      </h3>
      <table className="data-table">
        <thead>
          <tr>
            <th></th>
            <th>Category</th>
            <th>Path</th>
            <th>Size</th>
            <th>Last Modified</th>
          </tr>
        </thead>
        <tbody>
          {pendingItems.map((item) => (
            <tr key={item.item_id}>
              <td>
                <input
                  type="checkbox"
                  checked={checked.has(item.item_id)}
                  onChange={() => toggle(item.item_id)}
                />
              </td>
              <td>{item.category}</td>
              <td className="path-cell">{item.path}</td>
              <td>{formatBytes(item.size_bytes)}</td>
              <td>{item.last_modified}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button onClick={handleApprove} disabled={busy || checked.size === 0}>
        {busy ? "Processing…" : `Approve & Execute (${checked.size} selected)`}
      </button>
      {error && <p className="error">{error}</p>}
      <p className="hint">
        Approved items move to quarantine, not permanent deletion — recoverable within the hold window shown above.
      </p>
    </div>
  );
}

export default function Cleanup() {
  const [reports, setReports] = useState([]);
  const [error, setError] = useState(null);

  function load() {
    cleanupApi
      .listReports()
      .then(setReports)
      .catch((err) => setError(err.response?.data?.detail ?? err.message));
  }

  useEffect(load, []);

  if (error) return <p className="error">Failed to load cleanup reports: {error}</p>;

  const withPending = reports.filter((r) => r.items.some((i) => i.status === "pending_approval"));

  return (
    <div className="page cleanup-page">
      <h2>Category B — Cleanup Approval</h2>
      <p className="hint">
        Nothing here is deleted without your explicit approval. Uncheck anything you want to keep before approving.
      </p>
      {withPending.length === 0 && <p>No pending cleanup reports.</p>}
      {withPending.map((report) => (
        <ReportCard key={report.report_id} report={report} onApproved={load} />
      ))}
    </div>
  );
}
