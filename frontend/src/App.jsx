import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Building from "./pages/Building";
import Devices from "./pages/Devices";
import Rules from "./pages/Rules";
import Recommendations from "./pages/Recommendations";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";

export default function App() {
  const { user, loading } = useAuth();

  if (loading)
    return (
      <div style={{ display: "grid", placeItems: "center", height: "100vh" }}>
        <div className="spinner" />
      </div>
    );

  if (!user) return <Login />;

  // The Administrator (building owner) has no unit: their home is the building
  // overview, not a single-unit dashboard. Residents/developers get the unit views.
  const isAdmin = user.role === "admin";

  return (
    <Layout>
      <Routes>
        {isAdmin ? (
          <>
            <Route path="/" element={<Building />} />
            <Route path="/settings" element={<Settings />} />
          </>
        ) : (
          <>
            <Route path="/" element={<Dashboard />} />
            <Route path="/devices" element={<Devices />} />
            <Route path="/rules" element={<Rules />} />
            <Route path="/recommendations" element={<Recommendations />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/settings" element={<Settings />} />
          </>
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
