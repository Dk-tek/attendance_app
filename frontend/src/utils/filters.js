export const emptyFilters = {
  date: "",
  employee_id: ""
};

export function cleanFilters(filters) {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
}
