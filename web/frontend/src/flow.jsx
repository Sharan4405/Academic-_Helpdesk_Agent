import { useEffect, useState } from "react";
import { Check, Shield } from "./icons.jsx";

export const AGENT_LABEL = {
  helpdesk_orchestrator: "Orchestrator",
  policy_agent: "Policy agent",
  schedule_agent: "Schedule agent",
  email_agent: "Email agent",
  academic_helpdesk_single: "Single agent",
};

const short = (v) => {
  const s = typeof v === "string" ? v : JSON.stringify(v);
  return s.length > 70 ? s.slice(0, 67) + "…" : s;
};

/** Turn one streamed step into a line for the live timeline. */
export function describeStep(step) {
  if (step.type === "agent")
    return { icon: "agent", text: `${AGENT_LABEL[step.name] || step.name} is working` };
  if (step.type === "tool_call") {
    if (step.name === "transfer_to_agent")
      return {
        icon: "route",
        text: `Handed off to ${AGENT_LABEL[step.args.agent_name] || step.args.agent_name}`,
      };
    const args = Object.entries(step.args)
      .filter(([, v]) => v !== "" && v !== 0)
      .map(([k, v]) => `${k}=${short(v)}`)
      .join(", ");
    return { icon: "tool", text: `${step.name}(${args})`, mono: true };
  }
  if (step.type === "tool_result") {
    if (step.doc_ids?.length)
      return {
        icon: step.sufficient_evidence === false ? "warn" : "ok",
        text: `Retrieved ${step.doc_ids.join(", ")}${
          step.sufficient_evidence === false ? " — evidence insufficient" : ""
        }`,
      };
    return { icon: "ok", text: `${step.name} returned` };
  }
  return { icon: "agent", text: step.type };
}

function Countdown({ seconds, since }) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    const tick = () => setLeft(Math.max(0, Math.round(seconds - (Date.now() - since) / 1000)));
    tick();
    const id = setInterval(tick, 500);
    return () => clearInterval(id);
  }, [seconds, since]);
  return <>{left}s</>;
}

/** Live view while a turn runs: each step appears as the service reports it. */
export function LiveTimeline({ steps, wait }) {
  return (
    <ol className="timeline" aria-label="Agent progress">
      {steps.map((s, i) => {
        const d = describeStep(s);
        return (
          <li key={i} className={`tl-${d.icon}`}>
            <i />
            <span className={d.mono ? "mono" : ""}>{d.text}</span>
          </li>
        );
      })}
      {wait && (
        <li className="tl-wait">
          <i />
          <span>
            Free-tier token limit reached — retrying in <Countdown {...wait} />
          </span>
        </li>
      )}
      <li className="tl-now">
        <i />
        <span>{wait ? "Waiting" : "Thinking"}…</span>
      </li>
    </ol>
  );
}

/** Finished-turn pipeline: question → agents → tools → answer, from the trace. */
export function FlowDiagram({ turn }) {
  const calls = turn.tool_calls.filter((c) => c.name !== "transfer_to_agent");
  const refused = turn.tool_calls.some((c) => c.name === "log_unanswered_question");
  const specialist = turn.delegated_to;

  const byAgent = {};
  for (const c of calls) (byAgent[c.by] ||= []).push(c);

  const nodes = [{ kind: "start", title: "Student question" }];
  for (const a of turn.agents) {
    nodes.push({
      kind: a === specialist ? "specialist" : "agent",
      title: AGENT_LABEL[a] || a,
      tools: (byAgent[a] || []).map((c) => c.name),
    });
  }
  nodes.push(
    refused
      ? { kind: "refuse", title: "Refused & logged" }
      : { kind: "end", title: turn.email_draft ? "Draft for review" : "Cited answer" }
  );

  return (
    <div className="flow" role="img" aria-label="Agent flow for this answer">
      {nodes.map((n, i) => (
        <div key={i} className="flow-step">
          {i > 0 && <span className="flow-arrow">→</span>}
          <div className={`flow-node n-${n.kind}`}>
            <div className="flow-title">
              {n.kind === "refuse" && <Shield size={13} />}
              {n.kind === "end" && <Check size={13} />}
              {n.title}
            </div>
            {n.tools?.length > 0 && (
              <div className="flow-tools">
                {[...new Set(n.tools)].map((t) => (
                  <span key={t} className="mono">
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export function DraftCard({ draft }) {
  const [copied, setCopied] = useState(false);
  const text = `To: ${draft.to}\nCc: ${draft.cc}\nSubject: ${draft.subject}\n\n${draft.body}`;
  return (
    <div className="draft">
      <div className="draft-head">
        <strong>Email draft</strong>
        <span className="tag tag-accent">
          {draft.status === "draft_not_sent" ? "not sent" : draft.status}
        </span>
        <span className="spacer" />
        <button
          className="link"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(text);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            } catch {}
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <dl>
        <dt>To</dt>
        <dd>
          {draft.to} <span className="muted">({draft.instructor_name})</span>
        </dd>
        <dt>Cc</dt>
        <dd>{draft.cc}</dd>
        <dt>Subject</dt>
        <dd>{draft.subject}</dd>
      </dl>
      <pre>{draft.body}</pre>
      {draft.placeholders_to_fill?.length > 0 && (
        <div className="docs">
          <span className="muted small">Fill before sending:</span>
          {draft.placeholders_to_fill.map((p) => (
            <span key={p} className="tag">
              {p}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
