import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppContent } from "./App";

// Login is the only page that must render fully for the "no token -> login"
// path; the protected pages are mocked so we test routing/auth boundary without
// needing live backend data.
vi.mock("./pages/Overview", () => ({ default: () => <div /> }));
vi.mock("./pages/Alerts", () => ({ default: () => <div /> }));
vi.mock("./pages/Metrics", () => ({ default: () => <div /> }));
vi.mock("./pages/Tickets", () => ({ default: () => <div /> }));
vi.mock("./pages/Cleanup", () => ({ default: () => <div /> }));
vi.mock("./pages/RemoteAccess", () => ({ default: () => <div /> }));
vi.mock("./pages/Login", () => ({ default: () => <div>LOGIN</div> }));
vi.mock("./pages/DownloadAgent", () => ({ default: () => <div>DOWNLOAD</div> }));

describe("App routing / auth guard", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("redirects an unauthenticated user to /login", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppContent />
      </MemoryRouter>
    );
    expect(screen.getByText("LOGIN")).toBeInTheDocument();
  });

  it("renders protected content when a session token exists", () => {
    localStorage.setItem("aaditech_session_token", "abc");
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppContent />
      </MemoryRouter>
    );
    // With a token, ProtectedRoute renders the Layout; no LOGIN text shown.
    expect(screen.queryByText("LOGIN")).not.toBeInTheDocument();
  });

  it("serves the /downloads page WITHOUT requiring a session token", () => {
    // Download page is public: an unauthenticated fleet user (no token)
    // must still reach it, not be redirected to /login.
    render(
      <MemoryRouter initialEntries={["/downloads"]}>
        <AppContent />
      </MemoryRouter>
    );
    expect(screen.getByText("DOWNLOAD")).toBeInTheDocument();
    expect(screen.queryByText("LOGIN")).not.toBeInTheDocument();
  });
});