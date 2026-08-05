// Centralized API client. Every request goes through the Aaditech Portal
// backend (/api/*) — the frontend never talks to Wazuh/Zabbix/GLPI/
// MeshCentral/Grafana hosts directly, and never sees their URLs.
import axios from "axios";

const client = axios.create({
  baseURL: "/api",
  timeout: 15000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("aaditech_session_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("aaditech_session_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export const alertsApi = {
  list: (params) => client.get("/alerts/", { params }).then((r) => r.data),
  fim: (params) => client.get("/alerts/fim", { params }).then((r) => r.data),
  vulnerabilities: (params) => client.get("/alerts/vulnerabilities", { params }).then((r) => r.data),
  agentHealth: () => client.get("/alerts/agent-health").then((r) => r.data),
};

export const metricsApi = {
  hosts: () => client.get("/metrics/hosts").then((r) => r.data),
  triggers: (minSeverity) =>
    client.get("/metrics/triggers", { params: { min_severity: minSeverity } }).then((r) => r.data),
  itemHistory: (itemId, limit) =>
    client.get(`/metrics/items/${itemId}/history`, { params: { limit } }).then((r) => r.data),
};

export const ticketsApi = {
  create: (payload) => client.post("/tickets/", payload).then((r) => r.data),
  listOpen: () => client.get("/tickets/open").then((r) => r.data),
  get: (id) => client.get(`/tickets/${id}`).then((r) => r.data),
};

export const remoteApi = {
  startSession: (deviceId) => client.post("/remote/session", { device_id: deviceId }).then((r) => r.data),
  deviceStatus: (deviceId) => client.get(`/remote/devices/${deviceId}/status`).then((r) => r.data),
  endSession: (sessionId) => client.delete(`/remote/session/${sessionId}`).then((r) => r.data),
};

export const dashboardsApi = {
  embedUrl: (name) => client.get(`/dashboards/embed/${name}`).then((r) => r.data),
};

export const cleanupApi = {
  listReports: () => client.get("/cleanup/scan-reports").then((r) => r.data),
  getReport: (id) => client.get(`/cleanup/scan-reports/${id}`).then((r) => r.data),
  approve: (reportId, itemIds) =>
    client.post(`/cleanup/scan-reports/${reportId}/approve`, { item_ids: itemIds }).then((r) => r.data),
  restore: (reportId, itemId) =>
    client.post(`/cleanup/items/${reportId}/${itemId}/restore`).then((r) => r.data),
};

// Public (no auth) — used by the /downloads page and for GPO/Intune rollout.
export const agentInstallerApi = {
  info: () => client.get("/agent-installer").then((r) => r.data),
  downloadUrl: () => "/api/agent-installer/download",
};

export default client;
