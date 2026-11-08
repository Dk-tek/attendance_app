// Deliberately render a small formatting vocabulary as React nodes, never HTML.
export function inlineContent(text) {
  return text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("*") && part.endsWith("*")) return <em key={index}>{part.slice(1, -1)}</em>;
    const link = part.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
    if (link) return <a key={index} href={link[2]} target="_blank" rel="noopener noreferrer">{link[1]}</a>;
    return part;
  });
}
export function PolicyContent({ content }) {
  const nodes = []; let list = []; let ordered = false;
  function flush() { if (list.length) { const Tag = ordered ? "ol" : "ul"; nodes.push(<Tag key={nodes.length}>{list.map((line, i) => <li key={i}>{inlineContent(line)}</li>)}</Tag>); list = []; } }
  for (const line of content.split("\n")) {
    const item = line.match(/^(\s*[-*]|\d+\.)\s+(.+)/);
    if (item) { const isOrdered = /^\d/.test(item[1]); if (list.length && ordered !== isOrdered) flush(); ordered = isOrdered; list.push(item[2]); continue; }
    flush();
    const heading = line.match(/^(#{1,3})\s+(.+)/);
    if (heading) { const Tag = `h${heading[1].length + 1}`; nodes.push(<Tag key={nodes.length}>{inlineContent(heading[2])}</Tag>); }
    else if (line.trim()) nodes.push(<p key={nodes.length}>{inlineContent(line)}</p>);
  }
  flush(); return <article className="policyContent">{nodes}</article>;
}
