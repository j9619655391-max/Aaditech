import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import DownloadAgent from "./pages/DownloadAgent";
import Overview from "./pages/Overview";
import Alerts from "./pages/Alerts";
import Metrics from "./pages/Metrics";
import Tickets from "./pages/Tickets";
import Cleanup from "./pages/Cleanup";
import RemoteAccess from "./pages/RemoteAccess";

function isAuthenticated() {
  return Boolean(localStorage.getItem("aaditech_session_token"));
}

function ProtectedRoute({ children }) {
  return isAuthenticated() ? children : <Navigate to="/login" replace />;
}

export function AppContent() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/downloads" element={<DownloadAgent />} />
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Layout>
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/alerts" element={<Alerts />} />
                <Route path="/metrics" element={<Metrics />} />
                <Route path="/tickets" element={<Tickets />} />
                <Route path="/cleanup" element={<Cleanup />} />
                <Route path="/remote" element={<RemoteAccess />} />
              </Routes>
            </Layout>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}
