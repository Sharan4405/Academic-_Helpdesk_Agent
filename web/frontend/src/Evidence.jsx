import { useEffect, useMemo, useState } from "react";
import { search } from "./api.js";
import { Alert, Check, Layers, Search } from "./icons.jsx";

const STOP = new Set(["the", "and", "for", "what", "how", "are", "does", "with", "that", "this", "from"]);

function Highlight({ text, terms }) {
  if (!terms.length) return text;
  const re = new RegExp(`(${terms.join("|")})`, "gi");
  return text.split(re).map((part, i) =>
    i % 2 === 1 ? <mark key={i}>{part}</mark> : part
  );
}

function Meter({ distance, threshold }) {
  const over = distance > threshold;
  return (
    <div className="meter" title={`cosine distance ${distance} (threshold ${threshold})`}>
      <i className={over ? "over" : ""} style={{ width: Math.min(100, distance * 100) + "%" }} />
      <u style={{ left: Math.min(100, threshold * 100) + "%" }} />
    </div>
  );
}

function Hit({ hit, rank, threshold, cited, terms }) {
  const [open, setOpen] = useState(false);
  let where = hit.title;
  if (hit.page_start)
    where += hit.page_end && hit.page_end !== hit.page_start
      ? ` · pp. ${hit.page_start}–${hit.page_end}`
      : ` · p. ${hit.page_start}`;
  const long = hit.passage.length > 320;

  return (
    <article className={`hit${cited ? " cited" : ""}`}>
      <div className="hit-head">
        <span className="rank">{rank}</span>
        <strong>{hit.doc_id}</strong>
        <span className="tag">{hit.category.replace("_", " ")}</span>
        {cited && (
          <span className="tag tag-accent">
            <Check size={12} /> used by agent
          </span>
        )}
        <span className="spacer" />
        <span className="num" title="Re-rank score (similarity + lexical bonus)">
          {hit.score.toFixed(2)}
        </span>
      </div>
      <div className="where">{where}</div>
      <Meter distance={hit.distance} threshold={threshold} />
      <div className="dist muted small">cosine distance {hit.distance.toFixed(3)}</div>
      <p className={`passage${open ? " open" : ""}`}>
        <Highlight text={hit.passage} terms={terms} />
      </p>
      {long && (
        <button className="link" onClick={() => setOpen(!open)}>
          {open ? "Show less" : "Show full passage"}
        </button>
      )}
    </article>
  );
}

function Skeleton() {
  return (
    <div aria-busy="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="hit skeleton">
          <i style={{ width: "40%" }} />
          <i style={{ width: "70%" }} />
          <i style={{ width: "95%" }} />
          <i style={{ width: "85%" }} />
        </div>
      ))}
    </div>
  );
}

export default function Evidence({ status, agentSearch }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [topK, setTopK] = useState(5);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [cited, setCited] = useState(new Set());
  const [origin, setOrigin] = useState(""); // "agent" when mirrored from chat

  async function run(q, cat, k, citedIds, from) {
    if (!q.trim()) return;
    setBusy(true);
    setError("");
    try {
      setResult(await search(q, cat, k));
      setCited(new Set(citedIds));
      setOrigin(from);
    } catch (e) {
      setResult(null);
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  // Mirror the agent's own retrieval whenever a chat turn performs one.
  useEffect(() => {
    if (!agentSearch) return;
    setQuery(agentSearch.query);
    setCategory("");
    run(agentSearch.query, "", topK, agentSearch.docIds, "agent");
  }, [agentSearch]);

  const terms = useMemo(() => {
    if (!result) return [];
    const words = result.query
      .toLowerCase()
      .match(/[a-z]{3,}\d*|\d+%?/g) ?? [];
    return [...new Set(words.filter((w) => !STOP.has(w)))].map((w) =>
      w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    );
  }, [result]);

  return (
    <section className="card evidence">
      <div className="card-head">
        <div>
          <h2>Evidence</h2>
          <p className="muted small">
            What the vector store retrieves — no LLM involved
          </p>
        </div>
      </div>

      <form
        className="searchbar"
        onSubmit={(e) => {
          e.preventDefault();
          run(query, category, topK, [], "manual");
        }}
      >
        <div className="field">
          <Search size={16} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Try “attendance 75% Major examination” or AR-02.4"
            aria-label="Search query"
          />
        </div>
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          <option value="">All categories</option>
          {(status?.categories ?? []).map((c) => (
            <option key={c} value={c}>
              {c.replace("_", " ")}
            </option>
          ))}
        </select>
        <select value={topK} onChange={(e) => setTopK(+e.target.value)} aria-label="Results">
          {[3, 5, 8, 12].map((n) => (
            <option key={n} value={n}>
              Top {n}
            </option>
          ))}
        </select>
        <button className="btn" disabled={busy || !query.trim()}>
          Search
        </button>
      </form>

      <div className="results">
        {busy && !result && <Skeleton />}

        {!busy && !result && !error && (
          <div className="empty">
            <Layers size={28} />
            <h3>No search yet</h3>
            <p className="muted">
              Search the corpus directly, or ask a question in the chat — the passages the agent
              retrieves appear here.
            </p>
          </div>
        )}

        {error && (
          <div className="notice bad">
            <Alert size={16} /> {error}
          </div>
        )}

        {result && (
          <div className={busy ? "dim" : ""}>
            <div className={`verdict ${result.sufficient_evidence ? "ok" : "bad"}`}>
              <div className="verdict-title">
                {result.sufficient_evidence ? (
                  <>
                    <Check size={16} /> Sufficient evidence
                  </>
                ) : (
                  <>
                    <Alert size={16} /> Insufficient evidence
                  </>
                )}
              </div>
              <p>
                Best distance <b>{result.best_distance}</b>{" "}
                {result.sufficient_evidence ? "is within" : "exceeds"} the refusal threshold{" "}
                <b>{result.threshold}</b>.{" "}
                {result.sufficient_evidence
                  ? "The agent would answer from these passages."
                  : "The agent would refuse and log the question for a human."}
              </p>
              {origin === "agent" && (
                <p className="small muted">Showing the search the agent just ran.</p>
              )}
            </div>
            <div className="legend muted small">
              <span>
                <i className="swatch" /> distance (lower is closer)
              </span>
              <span>
                <u className="swatch-line" /> refusal threshold
              </span>
            </div>
            {result.results.map((h, i) => (
              <Hit
                key={`${h.doc_id}-${i}`}
                hit={h}
                rank={i + 1}
                threshold={result.threshold}
                cited={cited.has(h.doc_id)}
                terms={terms}
              />
            ))}
            {result.results.length === 0 && (
              <p className="muted">No passages matched this filter.</p>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
