// Building overview — the Administrator (building owner) view across every unit.
// Read-only: roster + per-unit power/bill + building totals, with drill-in to a
// single unit's dashboard. The owner never operates a resident's devices.
import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import { BAN, Loading, Empty, Pill, Modal } from "../components/ui";
import { Icon } from "../components/icons";
import { useAuth } from "../auth/AuthContext";
import { vnd, kwh, watts, deviceIconName, deviceColor } from "../lib/format";

export default function Building() {
  const { toast } = useAuth();
  const [ov, setOv] = useState(null);
  const [unit, setUnit] = useState(null); // {home_id, unit_name} being drilled into

  const load = useCallback(() => {
    api.buildingOverview().then(setOv).catch(() => {});
  }, []);

  // Soft offboard: deactivates + detaches the resident; the unit goes vacant but keeps
  // its devices and history. Destructive to access, so confirm first.
  const removeResident = async (u) => {
    if (!window.confirm(
      `Remove ${u.resident_name} from ${u.unit_name}?\n\n` +
      "The unit becomes vacant; its devices and billing history are kept."
    )) return;
    try {
      await api.offboardResident(u.home_id);
      toast(`${u.unit_name} is now vacant`, "ok");
      load();
    } catch (err) {
      toast(err.message || "Could not remove resident", "err");
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  if (!ov) return <Loading />;

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="grid cols-4">
        <BAN label="Units" value={ov.unit_count} accent="blue" icon={<Icon name="building" size={20} />} sub="In this building" />
        <BAN label="Residents" value={ov.resident_count} accent="purple" icon={<Icon name="users" size={20} />} sub="Onboarded tenants" />
        <BAN label="Live load" value={watts(ov.total_w)} accent="orange" icon={<Icon name="bolt" size={20} />} sub="All units combined" />
        <BAN
          label="Projected bill"
          value={vnd(ov.estimated_bill_vnd)}
          accent="green"
          icon={<Icon name="receipt" size={20} />}
          sub="This cycle, all units"
        />
      </div>

      <div className="card">
        <div className="card-title">
          <h2>Units</h2>
          <span className="muted" style={{ fontSize: 13 }}>
            {ov.kwh_cycle.toFixed(1)} kWh this cycle · building-wide
          </span>
        </div>
        {ov.units.length === 0 ? (
          <Empty>No units yet — onboard a resident in Settings.</Empty>
        ) : (
          <div className="stack" style={{ gap: 8 }}>
            {ov.units.map((u) => (
              <div key={u.home_id} className="between" style={{
                padding: "12px 14px", borderRadius: 10, background: "var(--c-surface-2)",
                flexWrap: "wrap", gap: 12,
              }}>
                <div style={{ minWidth: 200 }}>
                  <div style={{ fontWeight: 700 }}>{u.unit_name}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {u.resident_name ? `${u.resident_name} · ${u.resident_email}` : "Vacant"}
                  </div>
                </div>
                <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
                  <Metric label="Live" value={watts(u.total_w)} />
                  <Metric label="kWh cycle" value={kwh(u.kwh_cycle, 1)} />
                  <Metric label="Bill" value={vnd(u.estimated_bill_vnd)} />
                  <Pill kind={u.online_devices === u.total_devices ? "green" : "orange"}>
                    {u.online_devices}/{u.total_devices} reachable
                  </Pill>
                  <button
                    className="btn btn-sm"
                    onClick={() => setUnit({ home_id: u.home_id, unit_name: u.unit_name })}
                  >
                    View
                  </button>
                  {u.resident_email && (
                    <button className="btn btn-sm btn-ghost" onClick={() => removeResident(u)}>
                      Remove
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {unit && <UnitModal unit={unit} onClose={() => setUnit(null)} />}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div style={{ textAlign: "right", minWidth: 64 }}>
      <div className="muted" style={{ fontSize: 11 }}>{label}</div>
      <div className="tabular" style={{ fontWeight: 600, fontSize: 13.5 }}>{value}</div>
    </div>
  );
}

/* ---- read-only drill-in: one unit's live dashboard + device list ---- */
function UnitModal({ unit, onClose }) {
  const [dash, setDash] = useState(null);
  const [devices, setDevices] = useState([]);

  useEffect(() => {
    api.unitDashboard(unit.home_id).then(setDash).catch(() => {});
    api.unitDevices(unit.home_id).then(setDevices).catch(() => {});
  }, [unit.home_id]);

  return (
    <Modal title={`${unit.unit_name} · resident view (read-only)`} onClose={onClose} width={620}
      footer={<button className="btn" onClick={onClose}>Close</button>}>
      {!dash ? (
        <Loading />
      ) : (
        <div className="stack" style={{ gap: 14 }}>
          <div className="grid cols-3">
            <BAN label="Live load" value={watts(dash.home_total_w)} accent="orange" icon={<Icon name="bolt" size={20} />} />
            <BAN label="kWh today" value={kwh(dash.kwh_today, 1)} accent="blue" icon={<Icon name="activity" size={20} />} />
            <BAN label="Bill (cycle)" value={vnd(dash.estimated_bill_vnd)} accent="green" icon={<Icon name="receipt" size={20} />} />
          </div>
          <div className="stack" style={{ gap: 8 }}>
            {devices.map((d) => (
              <div key={d.id} className="between" style={{
                padding: "8px 12px", borderRadius: 10, background: "var(--c-surface-2)",
              }}>
                <div className="row" style={{ gap: 10 }}>
                  <Icon name={deviceIconName(d.type)} size={18} />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13.5 }}>{d.name}</div>
                    <div className="muted" style={{ fontSize: 11.5, color: deviceColor(d.type) }}>
                      {d.type} · {d.room}{d.safety_critical ? " · safety-critical" : ""}
                    </div>
                  </div>
                </div>
                <Pill kind={d.online ? "green" : "gray"}>{d.online ? "reachable" : "unreachable"}</Pill>
              </div>
            ))}
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            The building owner monitors units but does not operate their devices.
          </div>
        </div>
      )}
    </Modal>
  );
}
