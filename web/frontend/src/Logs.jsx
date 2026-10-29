import { useEffect, useState } from "react";
import { getDrafts, getUnanswered } from "./api.js";
import { DraftCard } from "./flow.jsx";

export default function Logs({ refreshKey }) {
  const [unanswered, setUnanswered] = useState([]);
  const [drafts, setDrafts] = useState([]);
  const [error, setError] = useState("");

  async function load() {
    try {
      const [u, d] = await Promise.all([getUnanswered(), getDrafts()]);
      setUnanswered(u);
      setDrafts(d);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
  }, [refreshKey]);

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Logs</h2>
          <p className="muted small">What the agents wrote to disk while answering</p>
        </div>
        <button className="btn-ghost" onClick={load}>
          Refresh
        </button>
      </div>
      <div className="results">
        {error && <div className="notice bad">{error}</div>}

        <h3 className="log-h">
          Unanswered questions <span className="muted small">— referred to a human</span>
        </h3>
        {unanswered.length === 0 && <p className="muted small">Nothing logged yet.</p>}
        {unanswered.map((u, i) => (
          <article key={i} className="hit">
            <div className="hit-head">
              <strong>{u.question}</strong>
              <span className="spacer" />
              <span className="tag">{u.reason_code.replace(/_/g, " ")}</span>
            </div>
            <div className="where">
              {u.timestamp.replace("T", " ")} · {u.status.replace(/_/g, " ")}
            </div>
            {u.notes && <p className="small">{u.notes}</p>}
          </article>
        ))}

        <h3 className="log-h">
          Email drafts <span className="muted small">— never sent</span>
        </h3>
        {drafts.length === 0 && <p className="muted small">No drafts yet.</p>}
        {drafts.map((d, i) => (
          <DraftCard key={i} draft={d} />
        ))}
      </div>
    </section>
  );
}
