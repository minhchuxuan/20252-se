// Small shared presentational components.
import { useEffect } from "react";

export function BAN({ label, value, unit, sub, accent = "blue", icon }) {
  const bg = {
    blue: "rgba(0,114,178,.12)",
    green: "rgba(0,158,115,.13)",
    orange: "rgba(230,159,0,.16)",
    red: "rgba(213,94,0,.13)",
  }[accent];
  return (
    <div className="card ban">
      {icon && <div className="ban-ico" style={{ background: bg }}>{icon}</div>}
      <div className="label">{label}</div>
      <div className={`value accent-${accent}`}>
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export function Pill({ kind = "gray", children }) {
  return <span className={`pill pill-${kind}`}>{children}</span>;
}

export function Modal({ title, onClose, children, footer, width }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" style={width ? { maxWidth: width } : undefined} onClick={(e) => e.stopPropagation()}>
        <div className="between" style={{ marginBottom: 16 }}>
          <h2 style={{ fontSize: 18 }}>{title}</h2>
          <button className="btn btn-sm btn-ghost" onClick={onClose}>✕</button>
        </div>
        {children}
        {footer && <div className="row" style={{ justifyContent: "flex-end", marginTop: 20 }}>{footer}</div>}
      </div>
    </div>
  );
}

export function Loading() {
  return (
    <div style={{ display: "grid", placeItems: "center", padding: 60 }}>
      <div className="spinner" />
    </div>
  );
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}
