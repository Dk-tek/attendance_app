export function PaginationControls({ pagination, onPageChange, onPageSizeChange }) {
  if (!pagination) return null;
  const pages = Array.from({ length: Math.min(5, pagination.pages) }, (_, i) => Math.max(1, Math.min(pagination.page - 2, pagination.pages - 4)) + i);

  return (
    <div className="paginationBar">
      <span className="recordCount">{pagination.total ? (pagination.page - 1) * pagination.page_size + 1 : 0}–{Math.min(pagination.page * pagination.page_size, pagination.total)} of {pagination.total} records</span>
      {onPageSizeChange ? <label className="pageSize">Rows<select aria-label="Rows per page" value={pagination.page_size} onChange={(e) => onPageSizeChange(Number(e.target.value))}>{[10, 20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}</select></label> : null}
      <button
        className="secondaryButton"
        type="button"
        disabled={!pagination.has_prev}
        onClick={() => onPageChange(pagination.page - 1)}
      >
        Previous
      </button>
      {pages.map((page) => <button type="button" key={page} className={page === pagination.page ? "primaryButton" : "secondaryButton"} aria-label={`Page ${page}`} aria-current={page === pagination.page ? "page" : undefined} onClick={() => onPageChange(page)}>{page}</button>)}
      <button
        className="secondaryButton"
        type="button"
        disabled={!pagination.has_next}
        onClick={() => onPageChange(pagination.page + 1)}
      >
        Next
      </button>
    </div>
  );
}
