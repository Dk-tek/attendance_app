import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { DataTable } from "../components/DataTable";
import { Loading, Notice } from "../components/Feedback";
import { PaginationControls } from "../components/PaginationControls";
import { useLoad } from "../hooks/useLoad";
import { cleanFilters } from "../utils/filters";
import { buildTimeline, eventLabels, matchingEmployees } from "../utils/monitoring";

const MapView = lazy(() => import("../components/MapView").then((module) => ({ default: module.MapView })));
const initialFilters = { q: "", employee_id: "", start: "", end: "" };

async function loadEmployees() {
  const users = [];
  let page = 1;
  do {
    const result = await api.listUsers({ page, page_size: 100, sort: "employee_name", direction: "asc" });
    users.push(...result.items);
    if (!result.pagination.has_next) return users;
    page++;
  } while (true);
}

export function MonitoringPage() {
  const [filters, setFilters] = useState(initialFilters);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selected, setSelected] = useState(null);
  const employees = useLoad(loadEmployees, [], 120000);
  function changeFilters(next) { setFilters(next); setPage(1); setSelected(null); }
  useEffect(() => {
    const timer = setTimeout(() => {
      if (search.trim() !== filters.q) { setFilters((value) => ({ ...value, q: search.trim() })); setPage(1); setSelected(null); }
    }, 300);
    return () => clearTimeout(timer);
  }, [search, filters.q]);
  const invalidRange = filters.start && filters.end && filters.start > filters.end;
  const query = { ...cleanFilters(filters), page, page_size: pageSize };
  const { data, error, loading } = useLoad(() => invalidRange ? Promise.resolve(null) : api.orgAttendance(query), [JSON.stringify(query), Boolean(invalidRange)]);
  const users = matchingEmployees(employees.data || [], search);
  const selectedUser = (employees.data || []).find((user) => user.employee_id === filters.employee_id);
  const options = selectedUser && !users.some((user) => user.employee_id === selectedUser.employee_id) ? [selectedUser, ...users] : users;

  return <div className="stack">
    <section className="monitorFilters panel">
      <label className="monitorSearch">Search employees<input type="search" placeholder="Name, employee ID or email" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <label>Employee<select aria-label="Employee" value={filters.employee_id} onChange={(event) => changeFilters({ ...filters, employee_id: event.target.value })}>
        <option value="">All employees</option>
        {options.map((user) => <option key={user.employee_id} value={user.employee_id}>{user.employee_name || user.employee_id} ({user.employee_id})</option>)}
      </select></label>
      <label>From date<input type="date" value={filters.start} max={filters.end || undefined} onChange={(event) => changeFilters({ ...filters, start: event.target.value })} /></label>
      <label>To date<input type="date" value={filters.end} min={filters.start || undefined} onChange={(event) => changeFilters({ ...filters, end: event.target.value })} /></label>
      <button className="secondaryButton" onClick={() => { setSearch(""); changeFilters(initialFilters); }}>Clear filters</button>
    </section>
    {invalidRange ? <Notice text="From date must be on or before To date." /> : null}
    {employees.error ? <Notice text={`Employee dropdown: ${employees.error}`} /> : null}
    {error ? <Notice text={error} /> : null}
    {loading ? <Loading /> : null}
    {!invalidRange && data ? <>
      <div className="sectionHead"><div><h2>Employee activity</h2><p className="muted">Select an employee day to inspect check-ins, GPS checkpoints and check-outs. Dates and times use IST.</p></div></div>
      <DataTable columns={["Employee", "Employee ID", "Date", "Check-ins", "Check-outs", "GPS points", "GPS failed", "Details"]} rows={(data.groups || []).map((group) => [
        group.employee_name || group.employee_id, group.employee_id, group.date, group.check_in_count, group.check_out_count, group.gps_count, group.failed_gps_count,
        <button className={selected?.employee_id === group.employee_id && selected?.date === group.date ? "primaryButton" : "secondaryButton"} onClick={() => setSelected(group)}>View timeline</button>
      ])} />
      <PaginationControls pagination={data.groups_pagination} onPageChange={(value) => { setPage(value); setSelected(null); }} onPageSizeChange={(value) => { setPageSize(value); setPage(1); setSelected(null); }} />
      {selected ? <MonitoringDetail key={`${selected.employee_id}:${selected.date}`} group={selected} onClose={() => setSelected(null)} /> : null}
    </> : null}
  </div>;
}

function MonitoringDetail({ group, onClose }) {
  const { data, loading, error } = useLoad(() => api.orgAttendance({ employee_id: group.employee_id, date: group.date, include_timeline: true }), [group.employee_id, group.date]);
  const events = useMemo(() => buildTimeline(data?.timeline), [data]);
  const [activeId, setActiveId] = useState(null);
  const timelineRef = useRef(null);
  useEffect(() => { timelineRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, []);
  function selectPoint(id) {
    setActiveId(id);
    const node = timelineRef.current?.querySelector(`[data-event-index="${events.findIndex((event) => event.id === id)}"]`);
    node?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  const currentId = events.some((event) => event.id === activeId) ? activeId : null;
  return <section className="panel stack" ref={timelineRef}>
    <div className="sectionHead"><div><p className="eyebrow">Activity timeline · IST</p><h2>{group.employee_name || group.employee_id}</h2><p className="muted">{group.employee_id} · {group.date} · {events.length} events</p></div><button className="secondaryButton" onClick={onClose}>Close details</button></div>
    {error ? <Notice text={error} /> : null}
    {loading ? <Loading /> : data ? <div className="monitorSplit">
      <div className="monitorTimeline"><p className="muted">Oldest first. Select a checkpoint to focus its map location.</p>
        {events.length ? <ol className="eventList">{events.map((event, index) => <li key={event.id} data-event-index={index}>
          <button className={`timelineEvent ${currentId === event.id ? "selected" : ""}`} aria-pressed={currentId === event.id} onClick={() => setActiveId(event.id)}>
            <span className={`eventNumber ${event.type}`}>{event.pointNumber ?? "–"}</span>
            <span className="eventCopy"><strong>{eventLabels[event.type] || event.type}</strong><time dateTime={event.timestamp}>{event.display_timestamp || event.timestamp}</time>
              <span>{event.pointNumber ? `${event.latitude.toFixed(6)}, ${event.longitude.toFixed(6)}` : event.tracking_status === "failed" ? "GPS failed · No map location" : "Location unavailable"}</span>
              {event.remark ? <span>{event.remark}</span> : null}
              {event.type === "check_out" ? <span>Source: {event.checkout_source || "Not recorded"}</span> : null}
            </span>
          </button>
        </li>)}</ol> : <p className="emptyState">No activity recorded for this employee day.</p>}
      </div>
      <Suspense fallback={<Loading />}><MapView points={events} numbered activePointId={currentId} onPointSelect={selectPoint} /></Suspense>
    </div> : null}
  </section>;
}
