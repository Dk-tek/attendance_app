export function Stat({ label, value, detail, icon: Icon }) {
  return (
    <article className="stat">
      <span className="statIcon">{Icon ? <Icon size={20} /> : null}</span>
      <p>{label}</p>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </article>
  );
}
