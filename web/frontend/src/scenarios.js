// The project brief's example questions, each with what a correct run must show.
// `checks` are evaluated against the finished turn so the UI can say pass/fail.

const has = (turn, name) => turn.tool_calls.some((c) => c.name === name);
const cited = (turn) => /sources?:/i.test(turn.answer) || turn.retrieved_doc_ids.length > 0;
const refused = (turn) => /do not know|don't know/i.test(turn.answer);

const routedTo = (agent) => ({
  label: `Routed to ${agent}`,
  test: (t) => t.delegated_to === agent,
});
const usedTool = (name) => ({ label: `Called ${name}`, test: (t) => has(t, name) });
const citesSource = { label: "Cites its source", test: cited };

const refusal = [
  { label: "Orchestrator refused without delegating", test: (t) => t.delegated_to === "" },
  usedTool("log_unanswered_question"),
  { label: 'Says "I do not know"', test: refused },
];

export const SCENARIOS = [
  {
    id: "attendance",
    group: "Rules & regulations (RAG)",
    question: "What is the attendance requirement to sit in the Major exam?",
    checks: [routedTo("policy_agent"), usedTool("search_academic_documents"), citesSource],
  },
  {
    id: "open-elective",
    group: "Rules & regulations (RAG)",
    question: "How many Open Elective credits do I need to earn in order to get a B.Tech. degree?",
    checks: [routedTo("policy_agent"), usedTool("search_academic_documents"), citesSource],
  },
  {
    id: "slot",
    group: "Timetable & slots (CSV tools)",
    question: "What is the slot for the course Autonomous Systems?",
    checks: [routedTo("schedule_agent"), usedTool("lookup_course"), citesSource],
  },
  {
    id: "count",
    group: "Timetable & slots (CSV tools)",
    question:
      "How many 400 level electives have been floated by the Humanities department in this semester?",
    checks: [routedTo("schedule_agent"), usedTool("find_courses"), citesSource],
  },
  {
    id: "email",
    group: "Email drafting",
    question: "Write an email to the course instructor of CSL7570 that I need leave for 2 days",
    checks: [
      routedTo("email_agent"),
      usedTool("lookup_course_instructor"),
      usedTool("draft_student_email"),
      {
        label: "Produced a draft with To and Subject, not sent",
        test: (t) =>
          !!t.email_draft &&
          !!t.email_draft.to &&
          !!t.email_draft.subject &&
          t.email_draft.status === "draft_not_sent",
      },
    ],
  },
  {
    id: "dining",
    group: "Must refuse, not guess",
    question: "What are the available dining options on the campus?",
    checks: refusal,
  },
  {
    id: "transport",
    group: "Must refuse, not guess",
    question: "What is the best way to reach the campus from Jodhpur city center?",
    checks: refusal,
  },
];

export function evaluate(scenario, turn) {
  return scenario.checks.map((c) => ({ label: c.label, ok: !!c.test(turn) }));
}
