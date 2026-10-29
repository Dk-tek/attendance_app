export function PaginationControls({ pagination, onPageChange }) {
  if (!pagination || pagination.pages <= 1) return null;

  return (
    <div className="paginationBar">
      <button
        className="secondaryButton"
        type="button"
        disabled={!pagination.has_prev}
        onClick={() => onPageChange(pagination.page - 1)}
      >
        Previous
      </button>
      <span>
        Page {pagination.page} of {pagination.pages} ({pagination.total} records)
      </span>
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
