import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

export function Modal({ title, onClose, dirty = false, busy = false, children }) {
  const dialog = useRef(null);
  const titleId = useId();
  const [discard, setDiscard] = useState(false);
  const closeRef = useRef(null);
  closeRef.current = () => { if (!busy) { if (dirty) setDiscard(true); else onClose(); } };
  useEffect(() => {
    const previous = document.activeElement;
    dialog.current.showModal();
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = oldOverflow; previous?.focus(); };
  }, []);
  return createPortal(
    <dialog ref={dialog} className="modal" aria-labelledby={titleId} onClick={(event) => { if (event.target.closest("[data-close-modal]")) closeRef.current(); }} onCancel={(event) => { event.preventDefault(); closeRef.current(); }}>
      <div className="sectionHead modalHead"><h2 id={titleId}>{title}</h2><button type="button" className="iconButton" aria-label="Close dialog" disabled={busy} onClick={() => closeRef.current()}><X size={18} /></button></div>
      {discard ? <div className="notice" role="alert"><p>Discard unsaved changes?</p><div className="actionsRow"><button type="button" className="dangerButton" onClick={onClose}>Discard changes</button><button type="button" className="secondaryButton" onClick={() => setDiscard(false)}>Keep editing</button></div></div> : null}
      {children}
    </dialog>, document.body);
}

export function ConfirmAction({ title, description, onConfirm, onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit() {
    setBusy(true); setError("");
    try { await onConfirm(); onClose(); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <Modal title={title} onClose={onClose} busy={busy}><p>{description}</p>{error ? <div className="notice error" role="alert">{error}</div> : null}<div className="modalFooter"><button className="secondaryButton" disabled={busy} onClick={onClose}>Cancel</button><button className="dangerButton" disabled={busy} onClick={submit}>{busy ? "Saving…" : "Confirm"}</button></div></Modal>;
}
