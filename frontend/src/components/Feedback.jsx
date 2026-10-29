export function Loading() {
  return <div className="notice">Loading...</div>;
}

export function Notice({ text }) {
  return <div className="notice error">{text}</div>;
}
