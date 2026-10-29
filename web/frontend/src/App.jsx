import { useEffect, useState } from "react";
import { getStatus } from "./api.js";
import Chat from "./Chat.jsx";
import Evidence from "./Evidence.jsx";
import Logs from "./Logs.jsx";
import Scenarios from "./Scenarios.jsx";
import { SCENARIOS, evaluate } from "./scenarios.js";
import { Cap } from "./icons.jsx";

function StatusPill({ ok, label, title }) {
  return (
    <span className={`pill ${ok ? "pill-ok" : "pill-bad"}`} title={title}>
      <i className="dot" />
      {label}
    </span>
  );
}

const TABS = [
  ["scenarios", "Scenarios"],
  ["evidence", "Evidence"],
  ["logs", "Logs"],
];

export default function App() {
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState("");
  const [tab, setTab] = useState("scenarios");
  const [mobilePane, setMobilePane] = useState("chat"); // narrow screens show one pane
  const [inject, setInject] = useState(null);
  const [results, setResults] = useState({});
  const [busy, setBusy] = useState(false);
  const [agentSearch, setAgentSearch] = useState(null);
  const [logKey, setLogKey] = useState(0);

  useEffect(() => {
    getStatus().then(setStatus).catch((e) => setStatusError(e.message));
  }, []);

  function runScenario(s) {
    setInject({ question: s.question, scenarioId: s.id, nonce: Date.now() });
    setMobilePane("chat");
  }

  function onTurn({ scenarioId, turn, error, seconds }) {
    setBusy(false);
    setLogKey((k) => k + 1);

    // Mirror the agent's own retrieval into the Evidence tab.
    const call = turn?.tool_calls.find((c) => c.name === "search_academic_documents");
    if (call?.args.query)
      setAgentSearch({ query: call.args.query, docIds: turn.retrieved_doc_ids, nonce: Date.now() });

    const scenario = SCENARIOS.find((s) => s.id === scenarioId);
    if (scenario)
      setResults((r) => ({
        ...r,
        [scenarioId]: error ? { error } : { checks: evaluate(scenario, turn), seconds },
      }));
  }

  const indexOk = !!status && status.chunks > 0;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">
            <Cap size={20} />
          </span>
          <div>
            <h1>Academic Helpdesk</h1>
            <p>IIT Jodhpur · multi-agent RAG demo</p>
          </div>
        </div>
        <div className="pills">
          {status ? (
            <>
              <StatusPill
                ok={indexOk}
                label={indexOk ? `${status.chunks} chunks · ${status.corpus}` : "Index empty"}
                title={`${status.embedding} · ${status.vector_backend} store`}
              />
              <StatusPill
                ok={status.chat_ready}
                label={status.chat_model}
                title={status.chat_issue || "Chat model configured"}
              />
            </>
          ) : (
            <StatusPill ok={false} label={statusError || "Connecting…"} />
          )}
        </div>
      </header>

      <nav className="tabs" role="tablist" aria-label="Panels">
        <button role="tab" aria-selected={mobilePane === "chat"} onClick={() => setMobilePane("chat")}>
          Chat
        </button>
        <button role="tab" aria-selected={mobilePane === "panel"} onClick={() => setMobilePane("panel")}>
          Scenarios · Evidence · Logs
        </button>
      </nav>

      <main>
        <div className={`pane ${mobilePane === "chat" ? "show" : ""}`}>
          <Chat status={status} inject={inject} onStart={() => setBusy(true)} onTurn={onTurn} />
        </div>
        <div className={`pane col ${mobilePane === "panel" ? "show" : ""}`}>
          <div className="segmented tabbar" role="tablist" aria-label="Side panel">
            {TABS.map(([id, label]) => (
              <button key={id} role="tab" aria-pressed={tab === id} onClick={() => setTab(id)}>
                {label}
              </button>
            ))}
          </div>
          {tab === "scenarios" && <Scenarios results={results} onRun={runScenario} busy={busy} />}
          {tab === "evidence" && <Evidence status={status} agentSearch={agentSearch} />}
          {tab === "logs" && <Logs refreshKey={logKey} />}
        </div>
      </main>
    </div>
  );
}
