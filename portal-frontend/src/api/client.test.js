import { describe, it, expect, vi, beforeEach } from "vitest";

// Hoisted mock for axios so ./client (imported below) gets a controllable
// instance when it calls `axios.create` at module load time. Static imports are
// hoisted above any top-level statements, so this MUST be set up before the
// static `import ... from "./client"`.
const { mockAxios } = vi.hoisted(() => {
  const instance = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  };
  const mockAxios = { create: vi.fn(() => instance), instance };
  return { mockAxios };
});

vi.mock("axios", () => ({ default: mockAxios }));

import {
  alertsApi,
  metricsApi,
  ticketsApi,
  remoteApi,
  dashboardsApi,
  cleanupApi,
} from "./client";

// axios.create was called exactly once, at module load, with the base config.
// beforeEach does vi.clearAllMocks(), which would wipe the call history before
// the baseURL test runs, so capture the config once here.
const createdWith = mockAxios.create.mock.calls[0][0];

describe("API client", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    mockAxios.instance.get.mockResolvedValue({ data: {} });
    mockAxios.instance.post.mockResolvedValue({ data: {} });
  });

  it("uses /api as the axios baseURL", () => {
    expect(createdWith).toEqual(expect.objectContaining({ baseURL: "/api" }));
  });

  it("exposes all feature API namespaces", () => {
    expect(alertsApi).toBeTruthy();
    expect(metricsApi).toBeTruthy();
    expect(ticketsApi).toBeTruthy();
    expect(remoteApi).toBeTruthy();
    expect(dashboardsApi).toBeTruthy();
    expect(cleanupApi).toBeTruthy();
  });
  it("cleanupApi.approve posts item_ids to the approve endpoint", async () => {
    mockAxios.instance.post.mockResolvedValue({ data: { approved_count: 1 } });
    const result = await cleanupApi.approve("report-1", ["item-a"]);
    expect(mockAxios.instance.post).toHaveBeenCalledWith(
      "/cleanup/scan-reports/report-1/approve",
      { item_ids: ["item-a"] }
    );
    expect(result.approved_count).toBe(1);
  });

  it("cleanupApi.restore posts to the item restore endpoint", async () => {
    mockAxios.instance.post.mockResolvedValue({ data: { command_id: "c1" } });
    const result = await cleanupApi.restore("report-1", "item-a");
    expect(mockAxios.instance.post).toHaveBeenCalledWith("/cleanup/items/report-1/item-a/restore");
    expect(result.command_id).toBe("c1");
  });

  it("dashboardsApi.embedUrl gets the signed embed url", async () => {
    mockAxios.instance.get.mockResolvedValue({ data: { embed_url: "/proxy", expires_at: 1 } });
    const result = await dashboardsApi.embedUrl("infra-overview");
    expect(mockAxios.instance.get).toHaveBeenCalledWith("/dashboards/embed/infra-overview");
    expect(result.embed_url).toBe("/proxy");
  });

  it("cleanupApi.listReports lists scan reports", async () => {
    mockAxios.instance.get.mockResolvedValue({ data: [{ report_id: "r1" }] });
    const result = await cleanupApi.listReports();
    expect(mockAxios.instance.get).toHaveBeenCalledWith("/cleanup/scan-reports");
    expect(result[0].report_id).toBe("r1");
  });
});