// Devices.jsx — capability-driven device management & control.
// Covers REQ-4.2.1 (capability schema drives the control UI), REQ-4.2.2..4.2.5
// (manual control, command outcomes, mock devices) and REQ-4.1.4 (offline
// detection via the connectivity toggle). The control panel itself is rendered
// by <DeviceControl/> straight from the capability schema — no per-type code.
import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import { BAN, Pill, Modal, Loading, Empty } from "../components/ui";
import DeviceControl from "../components/DeviceControl";
import { useAuth } from "../auth/AuthContext";
import { vndShort, kwh, watts, deviceColor, deviceIconName, fmtDateTime } from "../lib/format";
import { Icon } from "../components/icons";

// A device's instantaneous power lives in state.power_w; sensors report temp/occupancy.
const powerOf = (d) => Number((d.state && d.state.power_w) || 0);

export default function Devices() {
  const { user, toast } = useAuth();
  const [devices, setDevices] = useState(null); // null = loading
  const [adding, setAdding] = useState(false);
  const [control, setControl] = useState(null); // { device } currently in the control modal

  const canManage = user && (user.role === "admin" || user.role === "developer");

  const load = useCallback(async () => {
    try {
      const list = await api.devices();
      setDevices(list);
    } catch (err) {
      toast(err.message, "err");
      setDevices([]);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  // Replace a single device in the list (used after commands / connectivity flips).
  const patchDevice = useCallback((fresh) => {
    setDevices((list) => (list ? list.map((d) => (d.id === fresh.id ? fresh : d)) : list));
  }, []);

  const toggleConnectivity = async (device) => {
    const online = !device.online;
    try {
      const fresh = await api.setConnectivity(device.id, online);
      patchDevice(fresh);
      toast(`${device.name} ${online ? "back online" : "forced offline"}`, online ? "ok" : "warn");
    } catch (err) {
      toast(err.message, "err");
    }
  };

  const removeDevice = async (device) => {
    if (!window.confirm(`Delete "${device.name}"? This cannot be undone.`)) return;
    try {
      await api.deleteDevice(device.id);
      setDevices((list) => (list ? list.filter((d) => d.id !== device.id) : list));
      toast(`${device.name} deleted`, "ok");
    } catch (err) {
      toast(err.message, "err");
    }
  };

  if (devices === null) return <Loading />;

  // Sort by instantaneous power desc (busiest devices first).
  const sorted = [...devices].sort((a, b) => powerOf(b) - powerOf(a));
  const online = devices.filter((d) => d.online).length;
  const controllable = devices.filter((d) => d.type !== "sensor");
  const liveTotal = devices
    .filter((d) => d.online && d.type !== "sensor")
    .reduce((s, d) => s + powerOf(d), 0);

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="grid cols-4">
        <BAN label="Devices" value={devices.length} accent="blue" icon={<Icon name="puzzle" size={20} />}
          sub={`${controllable.length} controllable · ${devices.length - controllable.length} sensors`} />
        <BAN label="Online now" value={online} accent="green" icon={<Icon name="signal" size={20} />}
          sub={`${devices.length - online} offline`} />
        <BAN label="Live power" value={Math.round(liveTotal)} unit="W" accent="orange" icon={<Icon name="bolt" size={20} />}
          sub="Across online devices" />
        <BAN label="Safety-critical" value={devices.filter((d) => d.safety_critical).length}
          accent="red" icon={<Icon name="shield" size={20} />} sub="Protected from auto power-off" />
      </div>

      <div className="card">
        <div className="card-title">
          <h2>All devices</h2>
          {canManage && (
            <button className="btn btn-primary btn-sm" onClick={() => setAdding(true)}>
              ＋ Add mock device
            </button>
          )}
        </div>

        {sorted.length === 0 ? (
          <Empty>
            No devices yet.{canManage ? " Add a mock device to get started." : ""}
          </Empty>
        ) : (
          <div className="grid cols-3">
            {sorted.map((d) => (
              <DeviceCard
                key={d.id}
                device={d}
                canManage={canManage}
                onControl={() => setControl({ device: d })}
                onToggle={() => toggleConnectivity(d)}
                onDelete={() => removeDevice(d)}
              />
            ))}
          </div>
        )}
      </div>

      {control && (
        <ControlModal
          device={control.device}
          onClose={() => setControl(null)}
          toast={toast}
          onFresh={(fresh) => {
            patchDevice(fresh);
            setControl({ device: fresh });
          }}
        />
      )}

      {adding && (
        <AddDeviceModal
          onClose={() => setAdding(false)}
          toast={toast}
          onAdded={() => {
            setAdding(false);
            load();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- device card
function DeviceCard({ device, canManage, onControl, onToggle, onDelete }) {
  const d = device;
  const isSensor = d.type === "sensor";
  const color = deviceColor(d.type);

  // Sensors show temperature + occupancy; everything else shows live wattage.
  const occupied = d.state && d.state.occupancy;
  // Power switch state (on/off) is distinct from connectivity (online/offline):
  // a switchable device can be reachable yet powered off.
  const isOn = d.state && d.state.power === "on";
  const headline = isSensor
    ? (d.state && d.state.temperature != null ? `${Number(d.state.temperature).toFixed(1)}°C` : "—")
    : watts(powerOf(d));

  return (
    <div className="card" style={{ padding: 16, boxShadow: "none", background: "var(--c-surface-2)" }}>
      <div className="between">
        <span className="row" style={{ gap: 8 }}>
          <Icon name={deviceIconName(d.type)} size={22} />
          <span className="stack" style={{ gap: 2 }}>
            <span style={{ fontWeight: 700, fontSize: 14.5, lineHeight: 1.1 }}>{d.name}</span>
            <span className="muted" style={{ fontSize: 12 }}>{d.room}</span>
          </span>
        </span>
        <span className="row" style={{ gap: 6, fontSize: 12 }}>
          <span className={`dot ${d.online ? "dot-on" : "dot-off"}`} />
          {d.online ? "online" : "offline"}
        </span>
      </div>

      <div className="between" style={{ marginTop: 12 }}>
        <span className="tabular" style={{ fontSize: 22, fontWeight: 800, color }}>
          {headline}
        </span>
        <span className="muted tabular" style={{ fontSize: 12, textAlign: "right" }}>
          {kwh(d.kwh_total, 1)} total
        </span>
      </div>

      {isSensor && (
        <div className="row" style={{ gap: 6, marginTop: 8 }}>
          <Pill kind={occupied ? "green" : "gray"}>{occupied ? "occupied" : "vacant"}</Pill>
          {d.state && d.state.humidity != null && (
            <span className="muted tabular" style={{ fontSize: 12 }}>
              {Number(d.state.humidity).toFixed(0)}% RH
            </span>
          )}
        </div>
      )}

      <div className="row" style={{ gap: 6, marginTop: 10, flexWrap: "wrap" }}>
        {!isSensor && <Pill kind={isOn ? "green" : "gray"}>{isOn ? "on" : "off"}</Pill>}
        {d.safety_critical && <Pill kind="orange">safety-critical</Pill>}
        {d.is_mock && <Pill kind="blue">mock</Pill>}
      </div>

      <div className="muted" style={{ fontSize: 11.5, marginTop: 10 }}>
        Last seen {fmtDateTime(d.last_seen_at)}
      </div>

      <div className="row" style={{ gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        <button className="btn btn-sm" onClick={onControl}>Control</button>
        {canManage && (
          <>
            <button className="btn btn-sm btn-ghost" onClick={onToggle}>
              {d.online ? "Force offline" : "Bring online"}
            </button>
            <button className="btn btn-sm btn-danger" onClick={onDelete}>Delete</button>
          </>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------- control modal
function ControlModal({ device, onClose, onFresh, toast }) {
  const [cap, setCap] = useState(null);   // null = loading
  const [error, setError] = useState(null);

  useEffect(() => {
    let alive = true;
    setCap(null);
    setError(null);
    api
      .capabilities(device.id)
      .then((c) => alive && setCap(c))
      .catch((err) => {
        if (!alive) return;
        setError(err.message);
        toast(err.message, "err");
      });
    return () => {
      alive = false;
    };
    // Only refetch the schema when the device identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [device.id]);

  // Capability-driven command path (REQ-4.2.3/4.2.4). After every command we
  // refresh the device so the live toggles/sliders reflect the new state.
  const onCommand = async (controlName, value) => {
    let r;
    try {
      r = await api.command(device.id, controlName, value);
    } catch (err) {
      // e.g. resident role without permission -> backend 403 -> client throws.
      toast(err.message, "err");
      throw err;
    }
    if (r.outcome === "success") {
      toast(`${controlName} → ${value} ok`, "ok");
    } else {
      toast(r.detail || r.outcome, r.outcome === "rejected" ? "warn" : "err");
    }
    try {
      const fresh = await api.device(device.id);
      onFresh(fresh);
    } catch (err) {
      toast(err.message, "err");
    }
    return r;
  };

  const isSensor = device.type === "sensor";

  return (
    <Modal title={device.name} onClose={onClose} width={560}>
      <div className="between" style={{ marginBottom: 4 }}>
        <span className="row" style={{ gap: 8 }}>
          <Icon name={deviceIconName(device.type)} size={20} />
          <span className="muted" style={{ fontSize: 13 }}>{device.room}</span>
        </span>
        <span className="row" style={{ gap: 6, fontSize: 12 }}>
          <span className={`dot ${device.online ? "dot-on" : "dot-off"}`} />
          {device.online ? "online" : "offline"}
        </span>
      </div>

      {!device.online && (
        <div className="pill pill-red" style={{ marginBottom: 12 }}>
          Device offline — commands will time out (REQ-4.1.4)
        </div>
      )}

      {cap === null && !error && <Loading />}
      {error && <Empty>Could not load capabilities: {error}</Empty>}

      {cap && (
        <div className="stack" style={{ gap: 16 }}>
          {/* REQ-4.2.1 highlight: the schema that drives the control UI below. */}
          <div className="card" style={{ background: "var(--c-surface-2)", boxShadow: "none", padding: 14 }}>
            <div className="between" style={{ marginBottom: 8 }}>
              <h3 style={{ fontSize: 13 }}>Capability schema</h3>
              <span className="row" style={{ gap: 6 }}>
                <Pill kind="blue">{cap.display_name}</Pill>
                <Pill kind={cap.reversible ? "green" : "gray"}>
                  {cap.reversible ? "reversible" : "non-reversible"}
                </Pill>
                {cap.safety_critical && <Pill kind="orange">safety-critical</Pill>}
              </span>
            </div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>Telemetry channels</div>
            <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
              {cap.telemetry.length === 0 ? (
                <span className="muted" style={{ fontSize: 12 }}>none</span>
              ) : (
                cap.telemetry.map((t) => <Pill key={t} kind="gray">{t}</Pill>)
              )}
            </div>
            <div className="muted" style={{ fontSize: 11.5 }}>
              Controls below are rendered directly from this schema — no per-device code (REQ-4.2.1).
            </div>
          </div>

          <div className="card" style={{ boxShadow: "none", padding: "4px 16px" }}>
            {isSensor ? (
              <div className="muted" style={{ fontSize: 13, padding: 12 }}>
                This device is read-only (sensor). Live readings:{" "}
                {device.state && device.state.temperature != null
                  ? `${Number(device.state.temperature).toFixed(1)}°C`
                  : "—"}
                {device.state && device.state.occupancy != null && (
                  <> · {device.state.occupancy ? "occupied" : "vacant"}</>
                )}
              </div>
            ) : (
              <DeviceControl
                device={device}
                controls={cap.controls}
                disabled={!device.online}
                onCommand={onCommand}
              />
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

// --------------------------------------------------------- add mock device
function AddDeviceModal({ onClose, onAdded, toast }) {
  const [profiles, setProfiles] = useState(null); // null = loading
  const [picked, setPicked] = useState(null);     // selected profile type
  const [name, setName] = useState("");
  const [room, setRoom] = useState("Living room");
  const [safety, setSafety] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .mockProfiles()
      .then((p) => {
        if (!alive) return;
        setProfiles(p);
        if (p.length) {
          setPicked(p[0].type);
          setName(p[0].display_name);
        }
      })
      .catch((err) => {
        if (!alive) return;
        setProfiles([]);
        toast(err.message, "err");
      });
    return () => {
      alive = false;
    };
  }, [toast]);

  const selected = profiles && profiles.find((p) => p.type === picked);

  const submit = async () => {
    if (!picked || !name.trim()) {
      toast("Pick a profile and enter a name", "warn");
      return;
    }
    setBusy(true);
    try {
      await api.addDevice({
        name: name.trim(),
        type: picked,
        room: room.trim() || "Living room",
        safety_critical: safety,
      });
      toast(`${name.trim()} added`, "ok");
      onAdded();
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Add mock device"
      onClose={onClose}
      width={560}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-green" onClick={submit} disabled={busy || !picked}>
            {busy ? "Adding…" : "Add device"}
          </button>
        </>
      }
    >
      {profiles === null ? (
        <Loading />
      ) : profiles.length === 0 ? (
        <Empty>No mock profiles available.</Empty>
      ) : (
        <div className="stack" style={{ gap: 16 }}>
          <div>
            <label className="field">Device profile</label>
            <div className="grid cols-3" style={{ gap: 10 }}>
              {profiles.map((p) => {
                const on = p.type === picked;
                return (
                  <button
                    key={p.type}
                    type="button"
                    onClick={() => {
                      setPicked(p.type);
                      setName(p.display_name);
                    }}
                    className="card"
                    style={{
                      padding: 12,
                      textAlign: "left",
                      cursor: "pointer",
                      boxShadow: "none",
                      borderColor: on ? deviceColor(p.type) : "var(--c-border)",
                      background: on ? "rgba(0,114,178,.06)" : "var(--c-surface)",
                    }}
                  >
                    <div className="row" style={{ gap: 8 }}>
                      <Icon name={deviceIconName(p.type)} size={20} />
                      <span style={{ fontWeight: 700, fontSize: 13.5 }}>{p.display_name}</span>
                    </div>
                    <div className="muted tabular" style={{ fontSize: 11.5, marginTop: 6 }}>
                      ~{watts(p.nominal_power_w)} nominal · {p.controls.length} control
                      {p.controls.length === 1 ? "" : "s"}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {selected && (
            <div className="card" style={{ background: "var(--c-surface-2)", boxShadow: "none", padding: 12 }}>
              <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
                Telemetry this profile reports
              </div>
              <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                {selected.telemetry.map((t) => <Pill key={t} kind="gray">{t}</Pill>)}
              </div>
            </div>
          )}

          <div className="form-row" style={{ margin: 0 }}>
            <label className="field">Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Bedroom AC" />
          </div>

          <div className="form-row" style={{ margin: 0 }}>
            <label className="field">Room</label>
            <input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="Living room" />
          </div>

          <label className="row" style={{ gap: 10, fontSize: 13.5, fontWeight: 600, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={safety}
              onChange={(e) => setSafety(e.target.checked)}
              style={{ width: 16, height: 16 }}
            />
            <span>
              Mark as safety-critical
              <span className="muted" style={{ fontWeight: 400, display: "block", fontSize: 12 }}>
                Cannot be auto powered-off by rules (NFR-SAF-2)
              </span>
            </span>
          </label>
        </div>
      )}
    </Modal>
  );
}
