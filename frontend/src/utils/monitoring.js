import { validMapPoint } from "./mapPoints.js";

export const eventLabels = { check_in: "Check-in", check_out: "Check-out", location_track: "GPS checkpoint", attendance: "Attendance" };

export function buildTimeline(events = []) {
  let number = 0;
  const occurrences = new Map();
  return events.map((event, index) => ({ ...event, type: event.type || event.attendance_type || "attendance", sourceIndex: index }))
    .sort((a, b) => (Date.parse(a.timestamp) || 0) - (Date.parse(b.timestamp) || 0) || a.sourceIndex - b.sourceIndex)
    .map((event) => {
      const key = JSON.stringify([event.employee_id, event.session_id, event.type, event.timestamp, event.latitude, event.longitude, event.tracking_status]);
      const occurrence = occurrences.get(key) || 0;
      occurrences.set(key, occurrence + 1);
      return { ...event, id: `${key}:${occurrence}`, pointNumber: validMapPoint(event) ? ++number : null };
    });
}

export function matchingEmployees(users, search) {
  const query = search.trim().toLowerCase();
  return users.filter((user) => [user.employee_name, user.employee_id, user.email].some((value) => String(value || "").toLowerCase().includes(query)))
    .sort((a, b) => (a.employee_name || a.employee_id).localeCompare(b.employee_name || b.employee_id));
}
