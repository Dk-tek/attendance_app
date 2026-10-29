import { emptyFilters } from "../utils/filters";

export function FilterBar({ filters, setFilters, users = [] }) {
  return (
    <section className="filterBar">
      {users.length ? (
        <select value={filters.employee_id} onChange={(event) => setFilters({ ...filters, employee_id: event.target.value })}>
          <option value="">All employees</option>
          {users.map((user) => (
            <option key={user.user_id} value={user.employee_id}>
              {user.employee_name} ({user.employee_id})
            </option>
          ))}
        </select>
      ) : null}
      <input type="date" value={filters.date} onChange={(event) => setFilters({ ...filters, date: event.target.value })} />
      <button className="secondaryButton" onClick={() => setFilters(emptyFilters)}>Clear</button>
    </section>
  );
}
