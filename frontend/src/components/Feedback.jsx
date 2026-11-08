export function Loading() {
  return <div className="loadingState" role="status" aria-live="polite"><span className="spinner" />Loading workspace…</div>;
}

export function Notice({ text }) {
  return <div className="notice error" role="alert">{text}</div>;
}
