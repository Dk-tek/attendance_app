export const SITE_ORIGIN = "https://attendance.dreamcapture.in";
export const PUBLIC_URL = `${SITE_ORIGIN}/app/`;
export const HOME_SEO = {
  title: "Field Pixel | Face Attendance & GPS Field Tracking",
  description: "Manage your mobile workforce with Field Pixel: face-authenticated attendance, session GPS tracking, offline event sync, automatic checkout and organization dashboards.",
  indexable: true
};

const pages = {
  overview: ["Overview", "Review employee attendance, face enrollment, workforce capacity and active tracking sessions in your Field Pixel dashboard."],
  organizations: ["Organizations", "Manage Field Pixel organizations, administrators, employee limits, subscription pricing and account access."],
  plans: ["Subscription Plans", "Manage Field Pixel subscription plans with base pricing, per-user charges, billing cycles and organization assignments."],
  insights: ["Operational Insights", "Compare organization attendance, employee capacity and face enrollment coverage in Field Pixel."],
  users: ["Employees", "Manage employee accounts, access status and face enrollment for your Field Pixel organization."],
  attendance: ["Attendance & Location History", "Filter employee attendance by date, review check-in and checkout events, and explore recorded GPS locations on a map."],
  monitoring: ["Employee Monitoring", "Search employee activity by name, ID or email and inspect numbered GPS checkpoints in a timeline and map."],
  organization: ["Organization Details", "Review your Field Pixel organization, employee allocation, account status and assigned subscription."],
  subscription: ["Subscription & Pricing", "Review your Field Pixel plan, base price, per-user charges, registered employee count and billing-cycle total."],
  settings: ["Tracking Settings", "Review Field Pixel GPS tracking intervals, automatic checkout rules and organization attendance settings."],
  records: ["My Attendance Records", "Review your personal Field Pixel attendance history, including face-authenticated check-ins and checkout records."],
  map: ["My Location History", "Explore your recorded Field Pixel attendance and active-session GPS locations on an interactive map."],
  terms: ["Terms & Conditions", "Read the Terms & Conditions published by the Field Pixel Super Admin for organizations and employees using the attendance and field tracking platform."],
  privacy: ["Privacy Policy", "Read the Privacy Policy published by the Field Pixel Super Admin about personal information used in its attendance and field tracking platform."]
};

export function pageSeo(route, role, activePage) {
  if (!["#login", "#workspace"].includes(route)) return HOME_SEO;
  if (!role) return { title: "Sign In | Field Pixel", description: "Sign in to your Field Pixel account to access attendance, face authentication, GPS location history and your organization workspace.", indexable: false };
  const [label, description] = pages[activePage] || pages.overview;
  const roleName = { superadmin: "Super Admin", org_admin: "Org Admin", user: "Employee" }[role] || "Workspace";
  return { title: `${label} | ${roleName} | Field Pixel`, description, indexable: false };
}

export const PRODUCT_SCHEMA = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "Field Pixel",
  url: PUBLIC_URL,
  description: HOME_SEO.description,
  applicationCategory: "BusinessApplication",
  operatingSystem: "Web and mobile",
  image: `${PUBLIC_URL}field-pixel-logo.png`,
  featureList: ["Face-authenticated attendance", "GPS tracking during active sessions", "Offline tracking event sync", "Automatic checkout", "Attendance and location history", "Role-based organization management"]
};
