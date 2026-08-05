import { useEffect, useState } from "react";
import { ticketsApi } from "../api/client";

export default function Tickets() {
  const [openTickets, setOpenTickets] = useState([]);
  const [form, setForm] = useState({ title: "", description: "", urgency: 3 });
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  function loadTickets() {
    ticketsApi
      .listOpen()
      .then(setOpenTickets)
      .catch((err) => setError(err.message));
  }

  useEffect(loadTickets, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setMessage(null);
    setError(null);
    try {
      const result = await ticketsApi.create(form);
      setMessage(`Ticket #${result.id} created successfully.`);
      setForm({ title: "", description: "", urgency: 3 });
      loadTickets();
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page tickets-page">
      <h2>Tickets</h2>

      <form onSubmit={handleSubmit} className="ticket-form">
        <label>
          Title
          <input
            required
            minLength={3}
            maxLength={200}
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
        </label>
        <label>
          Description
          <textarea
            required
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </label>
        <label>
          Urgency
          <select
            value={form.urgency}
            onChange={(e) => setForm({ ...form, urgency: Number(e.target.value) })}
          >
            <option value={1}>Very Low</option>
            <option value={2}>Low</option>
            <option value={3}>Medium</option>
            <option value={4}>High</option>
            <option value={5}>Very High</option>
          </select>
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? "Creating…" : "Create Ticket"}
        </button>
        {message && <p className="success">{message}</p>}
        {error && <p className="error">{error}</p>}
      </form>

      <section>
        <h3>Open Tickets</h3>
        <ul>
          {openTickets.map((t) => (
            <li key={t.id}>
              #{t.id} — {t.name}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
