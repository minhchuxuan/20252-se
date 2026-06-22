import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api } from "../api/client";
import { useLiveFeed } from "../api/ws";
import { fmtDateTime } from "../lib/format";
import { Icon } from "./icons";

// The Administrator (building owner) oversees the whole building; residents and
// developers work within their own unit. The nav reflects each role's pages.
const ADMIN_NAV = [
  { to: "/", label: "Building", ico: "building", end: true },
  { to: "/settings", label: "Settings", ico: "settings" },
];

const UNIT_NAV = [
  { to: "/", label: "Dashboard", ico: "gauge", end: true },
  { to: "/devices", label: "Devices", ico: "plug" },
  { to: "/rules", label: "Rules & Automation", ico: "sliders" },
  { to: "/recommendations", label: "Recommendations", ico: "bulb" },
  { to: "/reports", label: "Reports", ico: "trending" },
  { to: "/settings", label: "Settings", ico: "settings" },
];

const TITLES = {
  "/devices": ["Devices", "Control devices through their capability schema"],
  "/rules": ["Rules & Automation", "WHEN-THEN rules, conflicts and auto-actions"],
  "/recommendations": ["Recommendations", "Explainable saving ideas from your habits"],
  "/reports": ["Reports", "Consumption history, top consumers and exports"],
  "/settings": ["Settings", "Tariff, residents and preferences"],
};

export default function Layout({ children }) {
  const { user, logout, toast } = useAuth();
  const loc = useLocation();
  const [notifs, setNotifs] = useState([]);
  const [open, setOpen] = useState(false);

  const load = () => api.notifications().then(setNotifs).catch(() => {});
  useEffect(() => {
    load();
  }, []);

  useLiveFeed((msg) => {
    if (msg.type === "notification") {
      toast(msg.notification?.title || "New notification", "ok");
      load();
    }
  });

  const isAdmin = user.role === "admin";
  const NAV = isAdmin ? ADMIN_NAV : UNIT_NAV;
  const homeTitle = isAdmin
    ? ["Building", "Live energy overview across every unit"]
    : ["Dashboard", "Live energy overview for your unit"];

  const unread = notifs.filter((n) => !n.read).length;
  const [title, sub] = (loc.pathname === "/" ? homeTitle : TITLES[loc.pathname]) || ["", ""];

  const markAll = async () => {
    await api.markAllRead();
    load();
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo"><Icon name="bolt" size={20} style={{ color: "#fff" }} /></div>
          <div className="brand-name">
            Energy Optimizer<small>Smart Home</small>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}>
              <span className="ico"><Icon name={n.ico} /></span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          IT3180E · v1.0
          <br />
          Mock-device demo build
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <h1>{title}</h1>
            <div className="sub">{sub}</div>
          </div>
          <div className="row" style={{ gap: 16 }}>
            <div style={{ position: "relative" }}>
              <button className="btn btn-ghost row" style={{ gap: 6 }} onClick={() => setOpen((o) => !o)} aria-label="Notifications">
                <Icon name="bell" />{unread > 0 && <span className="pill pill-red">{unread}</span>}
              </button>
              {open && (
                <div className="card" style={{ position: "absolute", right: 0, top: 46, width: 340, zIndex: 20, padding: 12 }}>
                  <div className="between" style={{ marginBottom: 8 }}>
                    <strong>Notifications</strong>
                    <button className="btn btn-sm btn-ghost" onClick={markAll}>Mark all read</button>
                  </div>
                  {notifs.length === 0 && <div className="empty">No notifications</div>}
                  <div className="stack" style={{ maxHeight: 340, overflow: "auto" }}>
                    {notifs.slice(0, 12).map((n) => (
                      <div key={n.id} style={{ opacity: n.read ? 0.55 : 1, borderBottom: "1px solid var(--c-border)", paddingBottom: 8 }}>
                        <div style={{ fontWeight: 600, fontSize: 13.5 }}>{n.title}</div>
                        <div className="muted" style={{ fontSize: 12.5 }}>{n.body}</div>
                        <div className="muted" style={{ fontSize: 11 }}>{fmtDateTime(n.ts)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="row">
              <div style={{ textAlign: "right" }}>
                <div style={{ fontWeight: 600, fontSize: 13.5 }}>{user.full_name}</div>
                <div className="muted" style={{ fontSize: 12 }}>{user.role}</div>
              </div>
              <button className="btn btn-sm" onClick={logout}>Logout</button>
            </div>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
