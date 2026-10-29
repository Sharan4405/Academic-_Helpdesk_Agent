import { useEffect, useRef, useState } from "react";
import { chatStream, resetSession } from "./api.js";
import Markdown, { splitSources } from "./markdown.jsx";
import { DraftCard, FlowDiagram, LiveTimeline } from "./flow.jsx";
import { Alert, Book, Cap, Check, Chevron, Copy, Plus, Send, Shield } from "./icons.jsx";

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

function BotMessage({ m, onRetry }) {
  if (m.status === "running")
    return (
      <div className="row bot">
        <div className="avatar">
          <Cap size={16} />
        </div>
        <div className="bubble">
          <LiveTimeline steps={m.steps} wait={m.wait} />
        </div>
      </div>
    );

  if (m.status === "failed")
    return (
      <div className="row bot">
        <div className="avatar bad">
          <Alert size={16} />
        </div>
        <div className="bubble error">
          <strong>Something went wrong</strong>
          <p>{m.error}</p>
          <button className="btn-sm" onClick={onRetry}>
            Try again
          </button>
        </div>
      </div>
    );

  const t = m.turn;
  const { body, sources } = splitSources(t.answer || "");
  const refused = t.tool_calls.some((c) => c.name === "log_unanswered_question");
  return (
    <div className="row bot">
      <div className="avatar">
        <Cap size={16} />
      </div>
      <div className="bubble">
        {refused && (
          <div className="refusal">
            <Shield size={14} /> Logged for a human — outside what the helpdesk can ground
          </div>
        )}
        <Markdown text={body || t.answer || "(no answer)"} />
        {t.email_draft && <DraftCard draft={t.email_draft} />}
        {t.error && <p className="err small">Agent error: {t.error}</p>}
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
          <details className="trace">
            <summary>
              <Chevron size={14} /> How this was answered
              <span className="muted"> · {Math.round(m.seconds)}s</span>
            </summary>
            <div className="trace-body">
              <FlowDiagram turn={t} />
              {t.retrieved_doc_ids.length > 0 && (
                <div className="docs">
                  {t.retrieved_doc_ids.map((d) => (
                    <span key={d} className="tag">
                      {d}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </details>
          <CopyButton text={t.answer} />
        </div>
      </div>
    </div>
  );
}

export default function Chat({ status, inject, onStart, onTurn }) {
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

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [input]);

  // A scenario started elsewhere in the app asks its question here.
  useEffect(() => {
    if (inject) ask(inject.question, inject.scenarioId);
  }, [inject]);

  async function ask(question, scenarioId) {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    onStart();
    const started = Date.now();
    setMessages((m) => [
      ...m,
      { role: "user", text: q },
      { role: "bot", status: "running", steps: [], wait: null, q, scenarioId },
    ]);
    const patch = (fn) => setMessages((m) => [...m.slice(0, -1), fn(m[m.length - 1])]);

    try {
      const turn = await chatStream(sessionId, q, mode, ({ event, data }) => {
        if (event === "step") patch((b) => ({ ...b, wait: null, steps: [...b.steps, data] }));
        if (event === "wait")
          patch((b) => ({ ...b, wait: { seconds: data.seconds, since: Date.now() } }));
      });
      const seconds = (Date.now() - started) / 1000;
      patch((b) => ({ ...b, status: "done", turn, seconds }));
      onTurn({ scenarioId, turn, seconds });
    } catch (e) {
      patch((b) => ({ ...b, status: "failed", error: e.message }));
      onTurn({ scenarioId, error: e.message });
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function retry(m) {
    setMessages((all) => all.slice(0, -2));
    ask(m.q, m.scenarioId);
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
          <p className="muted small">Watch the orchestrator route each question as it runs</p>
        </div>
        <div className="head-actions">
          <div className="segmented" role="group" aria-label="Agent mode">
            <button aria-pressed={mode === "multi"} onClick={() => setMode("multi")} disabled={busy}>
              Multi-agent
            </button>
            <button aria-pressed={mode === "single"} onClick={() => setMode("single")} disabled={busy}>
              Single
            </button>
          </div>
          <button className="btn-ghost" onClick={newChat} disabled={!messages.length || busy}>
            <Plus size={15} /> New chat
          </button>
        </div>
      </div>

      {status && !status.chat_ready && (
        <div className="notice">
          <Alert size={16} /> Chat is unavailable: {status.chat_issue}. Evidence search still works
          without a model.
        </div>
      )}

      <div className="log" ref={logRef} aria-live="polite">
        {messages.length === 0 ? (
          <div className="welcome">
            <h3>What do you need to know?</h3>
            <p className="muted">
              Ask about rules, curriculum, slots, exams or an email to an instructor. Open the{" "}
              <strong>Scenarios</strong> tab to run the project's required test questions and see
              whether each one passes.
            </p>
          </div>
        ) : (
          messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="row user">
                <div className="bubble">{m.text}</div>
              </div>
            ) : (
              <BotMessage key={i} m={m} onRetry={() => retry(m)} />
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
      <p className="hint">Enter to send · Shift+Enter for a new line · Email drafts are never sent</p>
    </section>
  );
}
