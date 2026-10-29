// A deliberately small markdown renderer: paragraphs, bullet/numbered lists,
// headings, **bold** and `code`. It builds React nodes, never HTML strings,
// so model output can't inject markup.

function inline(text, keyBase) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4)
      return <strong key={keyBase + i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2)
      return <code key={keyBase + i}>{part.slice(1, -1)}</code>;
    return part;
  });
}

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const HEADING = /^#{1,4}\s+(.*)$/;

export function splitSources(answer) {
  // Agents end every answer with a "Sources: ..." line.
  const m = answer.match(/\n?\s*\**Sources?:\**\s*(.+)\s*$/i);
  if (!m) return { body: answer, sources: [] };
  const sources = m[1]
    .split(/;|,(?![^(]*\))/)
    .map((s) => s.replace(/[*_`]/g, "").trim())
    .filter(Boolean);
  return { body: answer.slice(0, m.index).trimEnd(), sources };
}

export default function Markdown({ text }) {
  const blocks = [];
  let para = [];
  let list = null;

  const flushPara = () => {
    if (para.length) blocks.push({ type: "p", lines: para });
    para = [];
  };
  const flushList = () => {
    if (list) blocks.push(list);
    list = null;
  };

  for (const line of text.split("\n")) {
    let m;
    if (!line.trim()) {
      flushPara();
      flushList();
    } else if ((m = line.match(HEADING))) {
      flushPara();
      flushList();
      blocks.push({ type: "h", text: m[1] });
    } else if ((m = line.match(BULLET))) {
      flushPara();
      if (list?.type !== "ul") {
        flushList();
        list = { type: "ul", items: [] };
      }
      list.items.push(m[1]);
    } else if ((m = line.match(NUMBERED))) {
      flushPara();
      if (list?.type !== "ol") {
        flushList();
        list = { type: "ol", items: [] };
      }
      list.items.push(m[1]);
    } else {
      flushList();
      para.push(line);
    }
  }
  flushPara();
  flushList();

  return (
    <div className="md">
      {blocks.map((b, i) => {
        if (b.type === "h") return <h4 key={i}>{inline(b.text, `h${i}`)}</h4>;
        if (b.type === "ul" || b.type === "ol") {
          const Tag = b.type;
          return (
            <Tag key={i}>
              {b.items.map((it, j) => (
                <li key={j}>{inline(it, `l${i}-${j}`)}</li>
              ))}
            </Tag>
          );
        }
        return (
          <p key={i}>
            {b.lines.map((l, j) => (
              <span key={j}>
                {j > 0 && <br />}
                {inline(l, `p${i}-${j}`)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}
