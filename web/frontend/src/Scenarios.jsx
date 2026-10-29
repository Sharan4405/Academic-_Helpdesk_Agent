import { SCENARIOS } from "./scenarios.js";
import { Alert, Check } from "./icons.jsx";

function Badge({ result }) {
  if (!result) return <span className="tag">not run</span>;
  if (result.error)
    return (
      <span className="tag tag-bad">
        <Alert size={12} /> error
      </span>
    );
  const failed = result.checks.filter((c) => !c.ok).length;
  return failed === 0 ? (
    <span className="tag tag-ok">
      <Check size={12} /> pass
    </span>
  ) : (
    <span className="tag tag-bad">
      <Alert size={12} /> {failed} failed
    </span>
  );
}

export default function Scenarios({ results, onRun, busy }) {
  const groups = [...new Set(SCENARIOS.map((s) => s.group))];
  const passed = SCENARIOS.filter(
    (s) => results[s.id]?.checks && results[s.id].checks.every((c) => c.ok)
  ).length;

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>Requirement scenarios</h2>
          <p className="muted small">
            The brief's example questions. Each run is checked against what the agent must do.
          </p>
        </div>
        <span className="score">
          {passed}/{SCENARIOS.length} <span className="muted small">passed</span>
        </span>
      </div>
      <div className="results">
        {groups.map((g) => (
          <div key={g} className="sc-group">
            <h3>{g}</h3>
            {SCENARIOS.filter((s) => s.group === g).map((s) => {
              const r = results[s.id];
              return (
                <article key={s.id} className="scenario">
                  <div className="sc-head">
                    <p>{s.question}</p>
                    <button className="btn-sm" disabled={busy} onClick={() => onRun(s)}>
                      {r ? "Re-run" : "Run"}
                    </button>
                  </div>
                  <div className="sc-meta">
                    <Badge result={r} />
                    {r?.seconds && <span className="muted small">{Math.round(r.seconds)}s</span>}
                  </div>
                  {r?.error && <p className="err small">{r.error}</p>}
                  <ul className={`checks${r?.checks ? "" : " pending"}`}>
                    {(r?.checks ?? s.checks).map((c) => (
                      <li key={c.label} className={r?.checks ? (c.ok ? "ok" : "bad") : ""}>
                        <i>{r?.checks ? (c.ok ? "✓" : "✕") : "○"}</i> {c.label}
                      </li>
                    ))}
                  </ul>
                </article>
              );
            })}
          </div>
        ))}
        <p className="muted small">
          Timetable and slot questions use the CSV tools, not the document index. On a free-tier
          model a question can take a minute or more.
        </p>
      </div>
    </section>
  );
}
