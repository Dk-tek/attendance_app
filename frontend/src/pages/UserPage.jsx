import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { CalendarDays, CheckCircle2, LogOut, MapPinned } from "lucide-react";
import { api } from "../api";
import { DataTable } from "../components/DataTable";
import { FilterBar } from "../components/FilterBar";
import { Loading, Notice } from "../components/Feedback";
import { PaginationControls } from "../components/PaginationControls";
import { Stat } from "../components/Stat";
import { useLoad } from "../hooks/useLoad";
import { cleanFilters, emptyFilters } from "../utils/filters";

const MapView = lazy(() => import("../components/MapView").then((module) => ({ default: module.MapView })));

export function UserPage({ activePage }) {
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const query = useMemo(() => cleanFilters(filters), [filters]);
  useEffect(() => setPage(1), [query]);
  const { data, error, loading } = useLoad(
    () => api.userDashboard({ ...query, page, page_size: 20 }),
    [JSON.stringify(query), page],
  );

  if (loading) return <Loading />;
  if (error) return <Notice text={error} />;

  return (
    <div className="stack">
      {activePage === "overview" ? <UserOverview data={data} /> : null}
      {activePage === "records" ? (
        <>
          <FilterBar filters={filters} setFilters={setFilters} />
          <AttendanceRecords data={data} onPageChange={setPage} />
        </>
      ) : null}
      {activePage === "map" ? (
        <>
          <FilterBar filters={filters} setFilters={setFilters} />
          <Suspense fallback={<Loading />}>
            <MapView points={data.map_points} />
          </Suspense>
        </>
      ) : null}
    </div>
  );
}

function UserOverview({ data }) {
  return (
    <>
      <section className="statsGrid">
        <Stat label="Records" value={data.summary.attendance_records} detail="Filtered result" icon={CalendarDays} />
        <Stat label="Check-ins" value={data.summary.check_ins} detail="Arrival events" icon={CheckCircle2} />
        <Stat label="Check-outs" value={data.summary.check_outs} detail="Exit events" icon={LogOut} />
        <Stat label="Map points" value={data.summary.map_points} detail="Attendance and tracking" icon={MapPinned} />
      </section>
      <section className="panel prosePanel">
        <h2>My attendance monitoring</h2>
        <p>
          Review your check-in history, check-out history, and route points captured while attendance tracking is active.
        </p>
      </section>
    </>
  );
}

function AttendanceRecords({ data, onPageChange }) {
  return (
    <>
      <DataTable
        columns={["Type", "Latitude", "Longitude", "Time"]}
        rows={data.rows.map((row) => [
          row.attendance_type,
          row.latitude,
          row.longitude,
          row.display_timestamp || row.timestamp
        ])}
      />
      <PaginationControls pagination={data.pagination} onPageChange={onPageChange} />
    </>
  );
}
