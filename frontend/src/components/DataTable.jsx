export function DataTable({ columns, rows }) {
  return (
    <section className="panel tablePanel">
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length ? rows.map((row, index) => (
            <tr key={index}>
              {row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}
            </tr>
          )) : (
            <tr><td colSpan={columns.length}>No records found.</td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
