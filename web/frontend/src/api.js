async function request(path, body) {
  let r;
  try {
    r = await fetch(
      path,
      body === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
    );
  } catch {
    throw new Error("Can't reach the service. Is it running?");
  }
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail || detail;
    } catch {}
    throw new Error(detail);
  }
  return r.json();
}

export const getStatus = () => request("/api/status");
export const search = (query, category, top_k) =>
  request("/api/search", { query, category, top_k });
export const getUnanswered = () => request("/api/unanswered");
export const getDrafts = () => request("/api/email-drafts");
export const resetSession = (session_id) =>
  request(`/api/reset?session_id=${encodeURIComponent(session_id)}`, {});

/**
 * Run one agent turn. Calls onEvent({event, data}) for every server-sent event
 * ("step", "wait", "done", "fail") and resolves with the final payload.
 */
export async function chatStream(session_id, question, mode, onEvent) {
  let r;
  try {
    r = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id, question, mode }),
    });
  } catch {
    throw new Error("Can't reach the service. Is it running?");
  }
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail || detail;
    } catch {}
    throw new Error(detail);
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (!event || !data) continue;
      const parsed = JSON.parse(data);
      onEvent({ event, data: parsed });
      if (event === "done") result = parsed;
      if (event === "fail") throw new Error(parsed.error);
    }
  }
  if (!result) throw new Error("The service closed the stream before finishing.");
  return result;
}
