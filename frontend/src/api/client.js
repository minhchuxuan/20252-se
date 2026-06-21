// Thin REST client over fetch. One function per backend endpoint so pages never
// hand-build URLs. The bearer token is read from localStorage on each call.

const TOKEN_KEY = "sheo_token";
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY));

async function request(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const message = (data && (data.detail || data.message)) || `Request failed (${res.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data;
}

const get = (p) => request("GET", p);
const post = (p, b) => request("POST", p, b);
const patch = (p, b) => request("PATCH", p, b);
const put = (p, b) => request("PUT", p, b);
const del = (p) => request("DELETE", p);

// Authenticated CSV download -> triggers a browser save of the returned blob.
export async function downloadCsv(kind, filename) {
  const res = await fetch(`/api/reports/export/${kind}`, {
    headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
  });
  if (!res.ok) throw new Error(`Export failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const api = {
  // auth
  login: (email, password) => post("/auth/login", { email, password }),
  register: (body) => post("/auth/register", body),
  me: () => get("/auth/me"),
  addResident: (body) => post("/auth/residents", body),

  // devices + capability-driven control
  devices: () => get("/devices"),
  device: (id) => get(`/devices/${id}`),
  mockProfiles: () => get("/devices/profiles/mock"),
  addDevice: (body) => post("/devices", body),
  deleteDevice: (id) => del(`/devices/${id}`),
  capabilities: (id) => get(`/devices/${id}/capabilities`),
  command: (id, control, value) => post(`/devices/${id}/command`, { control, value }),
  setConnectivity: (id, online) => post(`/devices/${id}/connectivity?online=${online}`),

  // admin (building owner) — building-wide oversight
  buildingOverview: () => get("/admin/overview"),
  unitDashboard: (homeId) => get(`/admin/units/${homeId}/dashboard`),
  unitDevices: (homeId) => get(`/admin/units/${homeId}/devices`),

  // monitoring
  dashboard: () => get("/dashboard"),
  consumption: (range, deviceId) =>
    get(`/consumption?range=${range}${deviceId ? `&device_id=${deviceId}` : ""}`),
  topConsumers: (range, limit = 3) => get(`/top-consumers?range=${range}&limit=${limit}`),

  // rules
  rules: () => get("/rules"),
  validateRule: (body) => post("/rules/validate", body),
  createRule: (body) => post("/rules", body),
  updateRule: (id, body) => patch(`/rules/${id}`, body),
  deleteRule: (id) => del(`/rules/${id}`),
  ruleExecutions: (id) => get(`/rules/${id}/executions`),
  undoExecution: (id) => post(`/executions/${id}/undo`),

  // recommendations
  recommendations: () => get("/recommendations"),
  analyzeRecommendations: () => post("/recommendations/analyze"),
  acceptRecommendation: (id, body) => post(`/recommendations/${id}/accept`, body),
  dismissRecommendation: (id) => post(`/recommendations/${id}/dismiss`),

  // savings
  savingsSummary: () => get("/savings/summary"),
  savingsRecords: () => get("/savings/records"),
  estimate: (body) => post("/savings/estimate", body),

  // settings + tariff + notifications
  settings: () => get("/settings"),
  tariffs: () => get("/tariffs"),
  createTariff: (body) => post("/tariffs", body),
  activateTariff: (id) => put(`/tariffs/${id}/activate`),
  notifications: () => get("/notifications"),
  markRead: (id) => post(`/notifications/${id}/read`),
  markAllRead: () => post("/notifications/read-all"),

  // report exports (return URL for download)
  exportUrl: (kind) => `/api/reports/export/${kind}`,
};
