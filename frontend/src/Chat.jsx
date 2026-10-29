import { useEffect, useRef, useState } from "react";
import { chat, resetSession } from "./api.js";
import Markdown, { splitSources } from "./markdown.jsx";
import { Alert, Book, Check, Chevron, Copy, Plus, Send, Shield } from "./icons.jsx";

const SUGGESTIONS = [
  {
    tag: "Policy",
    q: "What is the attendance requirement to sit in the Major exam?",
  },
  {
    tag: "Curriculum",
    q: "How many Open Elective credits do I need for a B.Tech. degree?",
  },
  {
    tag: "Schedule",
    q: "What is the slot for the course Autonomous Systems?",
  },
  {
    tag: "Email draft",
    q: "Write an email to the course instructor of CSL7570 that I need leave for 2 days",
  },
  {
    tag: "Out of scope",
    q: "What are the available dining options on the campus?",
  },
];

const AGENT_LABEL = {
  helpdesk_orchestrator: "Orchestrator",
  policy_agent: "Policy",
  schedule_agent: "Schedule",
  email_agent: "Email",
};

const newId = () => "web-" + Math.random().toString(36).slice(2, 10);

function CopyButton({ text }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="icon-btn"
      title="Copy answer"
      aria-label="Copy answer"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {}
      }}
    >
      {done ? <Check size={15} /> : <Copy size={15} />}
    </button>
  );
}

function Trace({ turn }) {
  const calls = turn.tool_calls.filter((c) => c.name !== "transfer_to_agent");
  return (
    <details className="trace">
      <summary>
        <Chevron size={14} /> How this was answered
        <span className="muted">
          {" "}
          · {calls.length} tool call{calls.length === 1 ? "" : "s"}
        </span>
      </summary>
      <div className="trace-body">
        <div className="route">
          {turn.agents.map((a, i) => (
            <span key={a} className="route-step">
              {i > 0 && <span className="arrow">→</span>}
              <span className="badge">{AGENT_LABEL[a] || a}</span>
            </span>
          ))}
        </div>
        {calls.map((c, i) => {
          const args = Object.entries(c.args)
            .filter(([, v]) => v !== "" && v !== 0)
            .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
            .join(", ");
          return (
            <div key={i} className="call">
              <span className="call-name">{c.name}</span>
              {args && <span className="call-args">{args}</span>}
            </div>
          );
        })}
        {turn.retrieved_doc_ids.length > 0 && (
          <div className="docs">
            {turn.retrieved_doc_ids.map((d) => (
              <span key={d} className="tag">
                {d}
              </span>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

function BotMessage({ m, onRetry }) {
  if (m.pending)
    return (
      <div className="row bot">
        <div className="avatar">
          <Cap size={16} />
        </div>
        <div className="bubble typing" aria-label="Helpdesk is thinking">
          <i />
          <i />
          <i />
        </div>
      </div>
    );

  if (m.failed)
    return (
      <div className="row bot">
        <div className="avatar bad">
          <Alert size={16} />
        </div>
        <div className="bubble error">
          <strong>Something went wrong</strong>
          <p>{m.text}</p>
          <button className="btn-sm" onClick={onRetry}>
            Try again
          </button>
        </div>
      </div>
    );

  const { body, sources } = splitSources(m.text);
  const refused = m.turn.tool_calls.some((c) => c.name === "log_unanswered_question");
  return (
    <div className="row bot">
      <div className="avatar">
        <Cap size={16} />
      </div>
      <div className="bubble">
        {refused && (
          <div className="refusal">
            <Shield size={14} /> Referred to a human — outside what the helpdesk can ground
          </div>
        )}
        <Markdown text={body || m.text} />
        {m.turn.error && <p className="err small">Agent error: {m.turn.error}</p>}
        {sources.length > 0 && (
          <div className="sources">
            <Book size={14} />
            {sources.map((s) => (
              <span key={s} className="tag">
                {s}
              </span>
            ))}
          </div>
        )}
        <div className="bubble-foot">
          <Trace turn={m.turn} />
          <CopyButton text={m.text} />
        </div>
      </div>
    </div>
  );
}

export default function Chat({ status, onAgentSearch }) {
  const [sessionId, setSessionId] = useState(newId);
  const [mode, setMode] = useState("multi");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const logRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // Auto-grow the composer up to a cap.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [input]);

  async function ask(question) {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text: q }, { role: "bot", pending: true, q }]);
    const finish = (msg) => setMessages((m) => [...m.slice(0, -1), msg]);

    try {
      const turn = await chat(sessionId, q, mode);
      finish({ role: "bot", text: turn.answer || "(no answer)", turn, q });
      const call = turn.tool_calls.find((c) => c.name === "search_academic_documents");
      if (call?.args.query) {
        onAgentSearch({ query: call.args.query, docIds: turn.retrieved_doc_ids, nonce: Date.now() });
      }
    } catch (e) {
      finish({ role: "bot", failed: true, text: e.message, q });
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function retry(q) {
    setMessages((m) => m.slice(0, -2)); // drop the failed turn and its question
    ask(q);
  }

  function newChat() {
    resetSession(sessionId).catch(() => {});
    setSessionId(newId());
    setMessages([]);
  }

  return (
    <section className="card chat">
      <div className="card-head">
        <div>
          <h2>Ask the helpdesk</h2>
          <p className="muted small">Rules, curriculum, timetable, exams and email drafts</p>
        </div>
        <div className="head-actions">
          <div className="segmented" role="group" aria-label="Agent mode">
            <button aria-pressed={mode === "multi"} onClick={() => setMode("multi")}>
              Multi-agent
            </button>
            <button aria-pressed={mode === "single"} onClick={() => setMode("single")}>
              Single
            </button>
          </div>
          <button className="btn-ghost" onClick={newChat} disabled={!messages.length}>
            <Plus size={15} /> New chat
          </button>
        </div>
      </div>

      {status && !status.chat_ready && (
        <div className="notice">
          <Alert size={16} /> Chat is unavailable: {status.chat_issue}. The Evidence panel still
          works without a model.
        </div>
      )}

      <div className="log" ref={logRef} aria-live="polite">
        {messages.length === 0 ? (
          <div className="welcome">
            <h3>What do you need to know?</h3>
            <p className="muted">
              Every answer cites the official document it came from, and you can inspect the
              retrieved passages in the Evidence panel.
            </p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s.q} onClick={() => ask(s.q)} disabled={busy}>
                  <span className="tag">{s.tag}</span>
                  {s.q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="row user">
                <div className="bubble">{m.text}</div>
              </div>
            ) : (
              <BotMessage key={i} m={m} onRetry={() => retry(m.q)} />
            )
          )
        )}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
      >
        <textarea
          ref={inputRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask(input);
            }
          }}
          placeholder="Ask about attendance, credits, slots, exam dates…"
          aria-label="Your question"
        />
        <button className="send" disabled={busy || !input.trim()} aria-label="Send">
          <Send size={18} />
        </button>
      </form>
      <p className="hint">Enter to send · Shift+Enter for a new line · Drafts are never sent</p>
    </section>
  );
}
