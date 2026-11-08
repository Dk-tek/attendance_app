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
import { PolicyPage } from "./PolicyPage";

const MapView = lazy(() => import("../components/MapView").then((module) => ({ default: module.MapView })));

export function UserPage({ activePage }) {
  if (["terms", "privacy"].includes(activePage)) return <PolicyPage key={activePage} kind={activePage} />;
  return <UserDashboard activePage={activePage} />;
}

function UserDashboard({ activePage }) {
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const query = useMemo(() => cleanFilters(filters), [filters]);
  useEffect(() => setPage(1), [query]);
  const { data, error, loading } = useLoad(
    () => api.userDashboard({ ...query, page, page_size: pageSize }),
    [JSON.stringify(query), page, pageSize],
  );

  if (loading) return <Loading />;
  if (error) return <Notice text={error} />;

  return (
    <div className="stack">
      {activePage === "overview" ? <UserOverview data={data} /> : null}
      {activePage === "records" ? (
        <>
          <FilterBar filters={filters} setFilters={setFilters} />
          <AttendanceRecords data={data} onPageChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1); }} />
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

function AttendanceRecords({ data, onPageChange, onPageSizeChange }) {
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
      <PaginationControls pagination={data.pagination} onPageChange={onPageChange} onPageSizeChange={onPageSizeChange} />
    </>
  );
}
