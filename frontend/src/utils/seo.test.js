import test from "node:test";
import assert from "node:assert/strict";
import { pageSeo, PUBLIC_URL, PRODUCT_SCHEMA } from "./seo.js";

test("only the public product page is indexable on the correct canonical domain", () => {
  assert.equal(PUBLIC_URL, "https://attendance.dreamcapture.in/app/");
  assert.equal(pageSeo("#home", undefined, "overview").indexable, true);
  assert.equal(pageSeo("#capabilities", "superadmin", "terms").indexable, true);
  assert.equal(pageSeo("#login", undefined, "overview").indexable, false);
  assert.equal(PRODUCT_SCHEMA.url, PUBLIC_URL);
});

test("every workspace page has distinct metadata and stays private", () => {
  const keys = ["overview", "organizations", "plans", "insights", "users", "attendance", "monitoring", "organization", "subscription", "settings", "records", "map", "terms", "privacy"];
  const metadata = keys.map((page) => pageSeo("#workspace", "superadmin", page));
  assert.equal(new Set(metadata.map((page) => page.title)).size, keys.length);
  assert.equal(new Set(metadata.map((page) => page.description)).size, keys.length);
  for (const page of metadata) {
    assert.equal(page.indexable, false);
    assert.ok(page.title.includes("Field Pixel"));
    assert.ok(page.description.length > 70);
  }
});
