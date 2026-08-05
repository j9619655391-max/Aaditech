import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import Cleanup from "./Cleanup";
import { cleanupApi } from "../api/client";

vi.mock("../api/client", () => ({
  cleanupApi: {
    listReports: vi.fn(),
    getReport: vi.fn(),
    approve: vi.fn(),
    restore: vi.fn(),
  },
  default: {},
}));

const pendingReport = {
  report_id: "report-1",
  endpoint_name: "DESKTOP-01",
  triggered_by: "scheduled",
  items: [
    {
      item_id: "item-a",
      category: "windows_temp",
      path: "C:\\Windows\\Temp",
      size_bytes: 1500000,
      last_modified: "2026-08-01",
      status: "pending_approval",
    },
    {
      item_id: "item-b",
      category: "recycle_bin",
      path: "C:\\$Recycle.Bin",
      size_bytes: 500000,
      last_modified: "2026-08-01",
      status: "pending_approval",
    },
  ],
};

describe("Cleanup page", () => {
  beforeEach(() => {
    cleanupApi.listReports.mockResolvedValue([pendingReport]);
  });

  it("renders a pending report as a checklist with all items checked by default", async () => {
    render(<Cleanup />);
    await screen.findByText("DESKTOP-01");

    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes.length).toBe(2);
    checkboxes.forEach((cb) => expect(cb.checked).toBe(true));
    expect(
      screen.getByText(/Approve & Execute \(2 selected\)/)
    ).toBeInTheDocument();
  });

  it("calls approve with only the still-checked item_ids after one is unchecked", async () => {
    cleanupApi.approve.mockResolvedValue({ approved_count: 1 });
    const user = userEvent.setup();
    render(<Cleanup />);
    await screen.findAllByRole("checkbox");

    await user.click(screen.getAllByRole("checkbox")[0]);
    await user.click(screen.getByText(/Approve & Execute/));

    await waitFor(() =>
      expect(cleanupApi.approve).toHaveBeenCalledWith("report-1", ["item-b"])
    );
  });

  it("shows an error if the report list fails to load", async () => {
    cleanupApi.listReports.mockRejectedValue({
      response: { data: { detail: "server down" } },
    });
    render(<Cleanup />);
    await screen.findByText(/Failed to load cleanup reports: server down/);
  });
});