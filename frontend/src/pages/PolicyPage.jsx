import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useLoad } from "../hooks/useLoad";
import { Loading, Notice } from "../components/Feedback";
import { Modal } from "../components/Modal";
import { Badge, dateLabel } from "../components/Listing";
import { PolicyContent } from "../components/PolicyContent";

export function PolicyPage({ kind, editable = false }) {
  const { data, setData, loading, error } = useLoad(() => editable ? api.policy(kind) : api.publishedPolicy(kind), [kind, editable]);
  const [editing, setEditing] = useState(false);
  const [preview, setPreview] = useState(null);
  const [message, setMessage] = useState("");
  if (loading) return <Loading />;
  if (error) return <Notice text={error} />;
  const title = kind === "terms" ? "Terms & Conditions" : "Privacy Policy";
  return <div className="stack"><section className="panel"><div className="sectionHead"><div><h2>{title}</h2><p>{data.published ? `Published ${dateLabel(data.published.published_at)} · Version ${data.published.version}` : "No policy published yet"}</p></div>{editable ? <button className="primaryButton" onClick={() => setEditing(true)}>{data.revision ? "Edit policy" : "Create policy"}</button> : null}</div>
    {message ? <div role="status" className="notice">{message}</div> : null}
    <Badge active={!!data.published}>{data.published ? "Published" : "Unpublished"}</Badge>
    {editable && data.draft !== (data.published?.content || "") ? <div className="notice">An unpublished draft is saved. Last updated {dateLabel(data.updated_at)}.<button className="secondaryButton" onClick={() => setPreview(data.draft)}>Preview draft</button></div> : null}
    {data.published ? <PolicyContent content={data.published.content} /> : <div className="emptyState"><strong>{editable ? "Create the Field Pixel policy" : "No published content"}</strong><p>{editable ? "Save a draft, review the preview, then publish for all organizations and employees." : "The Super Admin has not published this policy yet."}</p></div>}
  </section>
  {editable && data.history?.length ? <section className="panel"><h2>Publication history</h2><div className="historyList">{[...data.history].reverse().map((entry) => <div className="sectionHead" key={entry.version}><span>Version {entry.version} · {dateLabel(entry.published_at)}</span><button className="secondaryButton" onClick={() => setPreview(entry.content)}>View version</button></div>)}</div></section> : null}
  {editing ? <PolicyEditor title={title} kind={kind} policy={data} onClose={() => setEditing(false)} onSaved={(value, published) => { setData(value); setEditing(false); setMessage(published ? "Policy published." : "Draft saved."); }} /> : null}
  {preview !== null ? <Modal title={`${title} preview`} onClose={() => setPreview(null)}><PolicyContent content={preview} /></Modal> : null}
  </div>;
}

function PolicyEditor({ title, kind, policy, onClose, onSaved }) {
  const [basePolicy] = useState(policy);
  const [content, setContent] = useState(basePolicy.draft || "");
  const [preview, setPreview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const editor = useRef(null);
  const dirty = content !== (basePolicy.draft || "");
  useEffect(() => { const warn = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } }; window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn); }, [dirty]);
  function insert(before, after = "") { const input = editor.current; const start = input.selectionStart, end = input.selectionEnd; const selected = content.slice(start, end) || "text"; setContent(content.slice(0, start) + before + selected + after + content.slice(end)); input.focus(); }
  async function save(publish) { setBusy(true); setError(""); try { const value = await api.savePolicy(kind, { content, revision: basePolicy.revision, publish }); onSaved(value, publish); } catch (err) { setError(err.message); } finally { setBusy(false); } }
  return <Modal title={`Edit ${title}`} onClose={onClose} dirty={dirty} busy={busy}><div className="actionsRow"><button className="secondaryButton" onClick={() => setPreview(!preview)}>{preview ? "Back to editor" : "Preview content"}</button><span className="muted">Basic formatting · {content.length.toLocaleString()} / 100,000</span></div>
    {preview ? <PolicyContent content={content} /> : <><div className="editorToolbar">{[["Heading", "\n## "], ["Bold", "**", "**"], ["Italic", "*", "*"], ["Bullet list", "\n- "], ["Numbered list", "\n1. "], ["Link", "[", "](https://example.com)"]].map(([label, before, after]) => <button key={label} className="secondaryButton" disabled={busy} onClick={() => insert(before, after)}>{label}</button>)}</div><label>Policy content<textarea ref={editor} disabled={busy} className="policyEditor" maxLength={100000} value={content} onChange={(e) => setContent(e.target.value)} /></label><p className="muted">Use # headings, **bold**, *italic*, lists and [link text](https://…). HTML is displayed as plain text.</p></>}
    {error ? <Notice text={error} /> : null}<div className="modalFooter"><button className="secondaryButton" disabled={busy} onClick={() => save(false)}>Save draft</button><button className="primaryButton" disabled={busy || !content.trim()} onClick={() => save(true)}>{busy ? "Saving…" : "Publish policy"}</button></div>
  </Modal>;
}
