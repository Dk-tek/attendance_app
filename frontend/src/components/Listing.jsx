import { useEffect, useState } from "react";
import { Search } from "lucide-react";

export function ListingTools({ query, onChange, sortOptions, children }) {
  const [search, setSearch] = useState(query.q);
  useEffect(() => { const timer = setTimeout(() => { if (search !== query.q) onChange({ ...query, q: search, page: 1 }); }, 300); return () => clearTimeout(timer); }, [search, query, onChange]);
  return <div className="listingTools"><label className="searchField"><Search size={17} /><input type="search" aria-label="Search records" placeholder="Search records…" value={search} onChange={(e) => setSearch(e.target.value)} /></label><label>Status<select value={query.status} onChange={(e) => onChange({ ...query, status: e.target.value, page: 1 })}><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select></label><label>Sort by<select value={query.sort} onChange={(e) => onChange({ ...query, sort: e.target.value, page: 1 })}>{sortOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button type="button" className="secondaryButton" aria-label="Reverse sort order" onClick={() => onChange({ ...query, direction: query.direction === "asc" ? "desc" : "asc", page: 1 })}>{query.direction === "asc" ? "Ascending ↑" : "Descending ↓"}</button>{children}</div>;
}

export const initialQuery = { page: 1, page_size: 10, q: "", status: "", sort: "created_at", direction: "desc" };
export function Badge({ active, children }) { return <span className={`badge ${active ? "positive" : "neutral"}`}>{children}</span>; }
export function dateLabel(value) { return value ? new Date(value).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" }) : "—"; }
