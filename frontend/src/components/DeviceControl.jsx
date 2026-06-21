// Capability-driven control renderer (REQ-4.2.1).
//
// Given a device's capability schema (controls[]), this renders the correct
// widget per control KIND — toggle / range / enum — with NO per-device-type
// branching. Adding a new device type on the backend automatically yields a
// working control panel here, with zero frontend changes.
import { useEffect, useState } from "react";

export default function DeviceControl({ device, controls, onCommand, disabled }) {
  const [vals, setVals] = useState({});
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    setVals(device.state || {});
  }, [device.id, device.state]);

  const send = async (control, value) => {
    setBusy(control);
    try {
      await onCommand(control, value);
    } finally {
      setBusy(null);
    }
  };

  if (!controls || controls.length === 0)
    return <div className="muted" style={{ fontSize: 13 }}>This device is read-only (sensor).</div>;

  return (
    <div>
      {controls.map((c) => {
        const current = vals[c.name];
        return (
          <div className="control-row" key={c.name}>
            <div>
              <div className="control-label">
                {c.label}
                {c.safety_sensitive && <span className="pill pill-orange" style={{ marginLeft: 8 }}>⚠ safety</span>}
              </div>
              <div className="control-meta">
                {c.kind === "range" && `range ${c.min}–${c.max}${c.unit ? " " + c.unit : ""}`}
                {c.kind === "enum" && c.values?.join(" · ")}
                {c.kind === "toggle" && "on / off"}
                {busy === c.name && " · sending…"}
              </div>
            </div>
            <div>
              {c.kind === "toggle" && (
                <label className="switch">
                  <input
                    type="checkbox"
                    disabled={disabled}
                    checked={String(current) === (c.values?.[0] ?? "on")}
                    onChange={(e) =>
                      send(c.name, e.target.checked ? (c.values?.[0] ?? "on") : (c.values?.[1] ?? "off"))
                    }
                  />
                  <span className="slider-toggle" />
                </label>
              )}

              {c.kind === "range" && (
                <div className="range-wrap">
                  <input
                    type="range"
                    min={c.min}
                    max={c.max}
                    step={c.step || 1}
                    disabled={disabled}
                    value={Number(current ?? c.min)}
                    onChange={(e) => setVals((v) => ({ ...v, [c.name]: Number(e.target.value) }))}
                    onMouseUp={(e) => send(c.name, Number(e.target.value))}
                    onTouchEnd={(e) => send(c.name, Number(e.target.value))}
                    onBlur={(e) => send(c.name, Number(e.target.value))}
                  />
                  <span className="range-val tabular">
                    {Number(current ?? c.min)}
                    {c.unit ? ` ${c.unit}` : ""}
                  </span>
                </div>
              )}

              {c.kind === "enum" && (
                <div className="seg">
                  {c.values.map((opt) => (
                    <button
                      key={opt}
                      disabled={disabled}
                      className={String(current) === opt ? "on" : ""}
                      onClick={() => send(c.name, opt)}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
