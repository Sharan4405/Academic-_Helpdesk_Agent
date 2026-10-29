import { useEffect, useState } from "react";
import { getStatus } from "./api.js";
import Chat from "./Chat.jsx";
import Evidence from "./Evidence.jsx";
import { Cap, Layers } from "./icons.jsx";

function StatusPill({ ok, label, title }) {
  return (
    <span className={`pill ${ok ? "pill-ok" : "pill-bad"}`} title={title}>
      <i className="dot" />
      {label}
    </span>
  );
}

export default function App() {
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState("");
  const [tab, setTab] = useState("chat"); // narrow screens show one panel at a time
  // When the agent searches, the evidence panel mirrors that query and marks
  // the documents the agent actually retrieved.
  const [agentSearch, setAgentSearch] = useState(null);

  useEffect(() => {
    getStatus().then(setStatus).catch((e) => setStatusError(e.message));
  }, []);

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
            <p>IIT Jodhpur · answers grounded in official documents</p>
          </div>
        </div>
        <div className="pills">
          {status ? (
            <>
              <StatusPill
                ok={indexOk}
                label={indexOk ? `${status.chunks} chunks indexed` : "Index empty"}
                title={status.embedding}
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
        <button role="tab" aria-selected={tab === "chat"} onClick={() => setTab("chat")}>
          Chat
        </button>
        <button role="tab" aria-selected={tab === "evidence"} onClick={() => setTab("evidence")}>
          <Layers size={15} /> Evidence
        </button>
      </nav>

      <main>
        <div className={`pane ${tab === "chat" ? "show" : ""}`}>
          <Chat status={status} onAgentSearch={setAgentSearch} />
        </div>
        <div className={`pane ${tab === "evidence" ? "show" : ""}`}>
          <Evidence status={status} agentSearch={agentSearch} />
        </div>
      </main>
    </div>
  );
}
