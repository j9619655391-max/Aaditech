import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/", label: "Overview" },
  { to: "/alerts", label: "Security Alerts" },
  { to: "/metrics", label: "Infra Metrics" },
  { to: "/tickets", label: "Tickets" },
  { to: "/cleanup", label: "Cleanup Approval" },
  { to: "/remote", label: "Remote Access" },
];

export default function Layout({ children }) {
  function logout() {
    localStorage.removeItem("aaditech_session_token");
    window.location.href = "/login";
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1 className="brand">Aaditech</h1>
        <nav>
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end className="nav-link">
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button onClick={logout} className="logout-btn">
          Log out
        </button>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
