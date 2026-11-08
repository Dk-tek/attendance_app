export function DataTable({ columns, rows }) {
  return (
    <section className="tablePanel" tabIndex={0} aria-label="Data table, scroll horizontally for more columns">
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
            <tr><td className="emptyState" colSpan={columns.length}><strong>No records found</strong><p>Try adjusting your search or filters.</p></td></tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
