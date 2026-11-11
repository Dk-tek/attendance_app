import test from "node:test";
import assert from "node:assert/strict";
import { buildTimeline, matchingEmployees } from "./monitoring.js";

test("timeline merges attendance and GPS chronologically and numbers only mapped events", () => {
  const events = buildTimeline([
    { attendance_type: "check_out", timestamp: "2026-11-11T12:00:00Z", latitude: 12, longitude: 77 },
    { type: "location_track", timestamp: "2026-11-11T10:00:00Z", tracking_status: "failed" },
    { attendance_type: "check_in", timestamp: "2026-11-11T09:00:00Z", latitude: 12, longitude: 77 },
    { type: "location_track", timestamp: "2026-11-11T11:00:00Z", latitude: 12.1, longitude: 77.1 },
    { attendance_type: "check_in", timestamp: "2026-11-11T08:00:00Z" },
  ]);
  assert.deepEqual(events.map((event) => event.type), ["check_in", "check_in", "location_track", "location_track", "check_out"]);
  assert.deepEqual(events.map((event) => event.pointNumber), [null, 1, null, 2, 3]);
  assert.equal(new Set(events.map((event) => event.id)).size, events.length);
});

test("employee dropdown matches name, employee ID and email without case sensitivity", () => {
  const users = [{ employee_id: "EMP002", employee_name: "Zoe", email: "zoe@example.com" }, { employee_id: "EMP001", employee_name: "Alex", email: "alex@example.com" }];
  for (const search of [" alex ", "emp001", "ALEX@EXAMPLE.COM"]) assert.equal(matchingEmployees(users, search)[0].employee_id, "EMP001");
  assert.deepEqual(matchingEmployees(users, "missing"), []);
  assert.deepEqual(matchingEmployees(users, "").map((user) => user.employee_name), ["Alex", "Zoe"]);
});

test("selected event identity survives refreshes with new events", () => {
  const original = { employee_id: "EMP001", type: "location_track", timestamp: "2026-11-11T10:00:00Z", latitude: 12, longitude: 77 };
  const added = { ...original, timestamp: "2026-11-11T11:00:00Z" };
  assert.equal(buildTimeline([original])[0].id, buildTimeline([added, original])[0].id);
});
