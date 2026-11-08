import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { DataTable } from "../components/DataTable";
import { FilterBar } from "../components/FilterBar";
import { Loading, Notice } from "../components/Feedback";
import { PaginationControls } from "../components/PaginationControls";
import { useLoad } from "../hooks/useLoad";
import { cleanFilters, emptyFilters } from "../utils/filters";

const MapView = lazy(() => import("../components/MapView").then((module) => ({ default: module.MapView })));

export function AttendanceExplorer({ users = [], onBack }) {
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const changeSize = (size) => { setPageSize(size); setPage(1); };
  const [selectedGroup, setSelectedGroup] = useState(null);
  const query = useMemo(() => {
    if (selectedGroup) {
      return {
        employee_id: selectedGroup.employee_id,
        date: selectedGroup.date
      };
    }
    return cleanFilters(filters);
  }, [filters, selectedGroup]);
  useEffect(() => {
    setPage(1);
    setSelectedGroup(null);
  }, [filters]);
  useEffect(() => setPage(1), [selectedGroup]);
  const { data, error, loading } = useLoad(
    () => api.orgAttendance({ ...query, page, page_size: pageSize }),
    [JSON.stringify(query), page, pageSize, selectedGroup?.employee_id, selectedGroup?.date],
  );

  return (
    <div className="stack">
      <div className="sectionHead">
        <h2>Attendance and location map</h2>
        {onBack ? <button className="secondaryButton" onClick={onBack}>Back</button> : null}
      </div>
      {!selectedGroup ? <FilterBar filters={filters} setFilters={setFilters} users={users} /> : null}
      {loading ? <Loading /> : null}
      {error ? <Notice text={error} /> : null}
      {data ? (
        selectedGroup ? (
          <AttendanceDetail
            data={data}
            selectedGroup={selectedGroup}
            onBack={() => setSelectedGroup(null)}
            onPageChange={setPage}
            onPageSizeChange={changeSize}
          />
        ) : (
          <AttendanceSummary data={data} onSelect={setSelectedGroup} onPageChange={setPage} onPageSizeChange={changeSize} />
        )
      ) : null}
    </div>
  );
}

function AttendanceSummary({ data, onSelect, onPageChange, onPageSizeChange }) {
  return (
    <>
      <DataTable
        columns={["Employee", "Date", "Check-ins", "Check-outs", "GPS points", "GPS failed", "First", "Last", "Action"]}
        rows={(data.groups || []).map((group) => [
          `${group.employee_name || group.employee_id}`,
          group.date,
          group.check_in_count,
          group.check_out_count,
          group.gps_count,
          group.failed_gps_count,
          group.first_time_display,
          group.last_time_display,
          <button className="secondaryButton" onClick={() => onSelect(group)}>View map</button>
        ])}
      />
      <PaginationControls pagination={data.groups_pagination} onPageChange={onPageChange} onPageSizeChange={onPageSizeChange} />
    </>
  );
}

function AttendanceDetail({ data, selectedGroup, onBack, onPageChange, onPageSizeChange }) {
  return (
    <>
      <div className="sectionHead">
        <div>
          <p className="eyebrow">Employee date view</p>
          <h2>{selectedGroup.employee_name || selectedGroup.employee_id} - {selectedGroup.date}</h2>
        </div>
        <button className="secondaryButton" onClick={onBack}>Back to dates</button>
      </div>
      <Suspense fallback={<Loading />}>
        <MapView points={data.map_points} />
      </Suspense>
      <DataTable
        columns={["GPS status", "Remark", "Time"]}
        rows={(data.map_points || []).filter((point) => point.tracking_status === "failed").map((point) => [point.tracking_status, point.remark, point.display_timestamp || point.timestamp])}
      />
      <DataTable
        columns={["Type", "Latitude", "Longitude", "Remark", "Time"]}
        rows={data.rows.map((row) => [
          row.attendance_type,
          row.latitude,
          row.longitude,
          row.remark || row.checkout_source || "",
          row.display_timestamp || row.timestamp
        ])}
      />
      <PaginationControls pagination={data.pagination} onPageChange={onPageChange} onPageSizeChange={onPageSizeChange} />
    </>
  );
}
