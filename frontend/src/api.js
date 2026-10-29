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
    throw new Error("Can't reach the server. Is it running?");
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
export const chat = (session_id, question, mode) =>
  request("/api/chat", { session_id, question, mode });
export const resetSession = (session_id) =>
  request(`/api/reset?session_id=${encodeURIComponent(session_id)}`, {});
