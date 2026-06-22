// Rules page — WHEN-THEN automation rules, conflict detection, pre-save VND
// estimate, auto-action opt-in (REQ-4.3.6) and the 2-minute undo window.
// Covers REQ-4.3.1..4.3.6 and REQ-4.5.3 (estimate shown BEFORE saving).
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { BAN, Empty, Loading, Modal, Pill } from "../components/ui";
import {
  deviceColor,
  deviceIconName,
  fmtDateTime,
  vnd,
  vndShort,
} from "../lib/format";
import { Icon } from "../components/icons";
import { useAuth } from "../auth/AuthContext";

const WHEN_TYPES = [
  { value: "time", label: "Time of day" },
  { value: "occupancy", label: "Room occupancy" },
  { value: "day", label: "Day of week" },
  { value: "device_state", label: "Another device's state" },
  { value: "tariff_window", label: "Tariff window" },
];
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const TARIFF_WINDOWS = ["peak", "offpeak", "normal"];
const STATE_OPS = [
  { value: "eq", label: "=" },
  { value: "ne", label: "≠" },
  { value: "gt", label: ">" },
  { value: "lt", label: "<" },
];

// outcome -> pill kind
const OUTCOME_KIND = {
  success: "green",
  rejected: "red",
  timeout: "red",
  skipped: "gray",
};

// ---- value widget shared by THEN action + device_state condition ----------
function ControlValueInput({ control, value, onChange }) {
  if (!control) return <input value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
  if (control.kind === "toggle") {
    const allowed = control.values?.length ? control.values : ["on", "off"];
    return (
      <select value={value ?? allowed[0]} onChange={(e) => onChange(e.target.value)}>
        {allowed.map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
    );
  }
  if (control.kind === "enum") {
    return (
      <select value={value ?? control.values?.[0] ?? ""} onChange={(e) => onChange(e.target.value)}>
        {(control.values || []).map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
    );
  }
  if (control.kind === "range") {
    return (
      <input
        type="number"
        min={control.min}
        max={control.max}
        step={control.step || 1}
        value={value ?? control.min ?? 0}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    );
  }
  return <input value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
}

// ---- New rule builder modal -----------------------------------------------
function RuleBuilder({ devices, onClose, onSaved }) {
  const { toast } = useAuth();
  // target device for the THEN action (no sensors — they're read-only)
  const targets = useMemo(() => devices.filter((d) => d.type !== "sensor"), [devices]);
  const sensors = useMemo(() => devices.filter((d) => d.type === "sensor"), [devices]);

  const [name, setName] = useState("");
  const [deviceId, setDeviceId] = useState(targets[0]?.id ?? "");
  const [caps, setCaps] = useState(null); // capability schema for the target device
  const [autoApply, setAutoApply] = useState(false);

  // WHEN builder state
  const [whenType, setWhenType] = useState("time");
  const [timeMode, setTimeMode] = useState("at"); // "at" | "between"
  const [timeAt, setTimeAt] = useState("18:00");
  const [timeFrom, setTimeFrom] = useState("18:00");
  const [timeTo, setTimeTo] = useState("23:00");
  const [occSensor, setOccSensor] = useState(sensors[0]?.id ?? "");
  const [occValue, setOccValue] = useState("false"); // "false"=empty, "true"=occupied
  const [occMinutes, setOccMinutes] = useState(10);
  const [dayDays, setDayDays] = useState(["mon", "tue", "wed", "thu", "fri"]);
  const [stDevice, setStDevice] = useState(devices[0]?.id ?? "");
  const [stCaps, setStCaps] = useState(null);
  const [stControl, setStControl] = useState("");
  const [stOp, setStOp] = useState("eq");
  const [stValue, setStValue] = useState("");
  const [tariffWindow, setTariffWindow] = useState("peak");

  // THEN builder state
  const [thenControl, setThenControl] = useState("");
  const [thenValue, setThenValue] = useState(null);

  // validation
  const [validation, setValidation] = useState(null);
  const [validating, setValidating] = useState(false);
  const [saving, setSaving] = useState(false);

  // load capabilities of the THEN target device
  useEffect(() => {
    if (!deviceId) { setCaps(null); return; }
    let alive = true;
    api.capabilities(deviceId)
      .then((c) => { if (alive) setCaps(c); })
      .catch((err) => toast(err.message, "err"));
    return () => { alive = false; };
  }, [deviceId, toast]);

  // when caps load, default the THEN control + value
  useEffect(() => {
    const ctrls = caps?.controls || [];
    if (ctrls.length) {
      const first = ctrls[0];
      setThenControl(first.name);
      setThenValue(defaultControlValue(first));
    } else {
      setThenControl("");
      setThenValue(null);
    }
    setValidation(null);
  }, [caps]);

  // load capabilities of the device_state condition device
  useEffect(() => {
    if (whenType !== "device_state" || !stDevice) { setStCaps(null); return; }
    let alive = true;
    api.capabilities(stDevice)
      .then((c) => { if (alive) setStCaps(c); })
      .catch((err) => toast(err.message, "err"));
    return () => { alive = false; };
  }, [whenType, stDevice, toast]);

  useEffect(() => {
    const ctrls = stCaps?.controls || [];
    if (ctrls.length) {
      setStControl(ctrls[0].name);
      setStValue(defaultControlValue(ctrls[0]));
    }
  }, [stCaps]);

  const thenCtrlObj = (caps?.controls || []).find((c) => c.name === thenControl) || null;
  const stCtrlObj = (stCaps?.controls || []).find((c) => c.name === stControl) || null;

  const toggleDay = (d) =>
    setDayDays((s) => (s.includes(d) ? s.filter((x) => x !== d) : [...s, d]));

  // assemble the WHEN condition payload
  const buildWhen = () => {
    if (whenType === "time")
      return timeMode === "at"
        ? { type: "time", at: timeAt }
        : { type: "time", between: [timeFrom, timeTo] };
    if (whenType === "occupancy")
      return {
        type: "occupancy",
        device_id: Number(occSensor),
        value: occValue === "true",
        for_minutes: Number(occMinutes),
      };
    if (whenType === "day") return { type: "day", days: dayDays };
    if (whenType === "device_state")
      return {
        type: "device_state",
        device_id: Number(stDevice),
        control: stControl,
        op: stOp,
        value: stValue,
      };
    return { type: "tariff_window", window: tariffWindow };
  };

  const buildBody = () => ({
    name: name.trim(),
    device_id: Number(deviceId),
    when: buildWhen(),
    then: { control: thenControl, value: thenValue },
    until: null,
    enabled: true,
    auto_apply: autoApply,
  });

  // any builder edit invalidates a previous "valid" result -> force re-check
  const dirty = () => setValidation(null);

  const onValidate = async () => {
    setValidating(true);
    try {
      const res = await api.validateRule(buildBody());
      setValidation(res);
      if (!res.valid) toast("Rule has issues — see details", "warn");
      else toast("Rule looks good", "ok");
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setValidating(false);
    }
  };

  const onSave = async () => {
    setSaving(true);
    try {
      await api.createRule(buildBody());
      toast("Rule created", "ok");
      onSaved();
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setSaving(false);
    }
  };

  const canSave = validation?.valid && name.trim() && deviceId && thenControl;

  return (
    <Modal title="New rule" width={620} onClose={onClose}>
      <div className="stack" style={{ gap: 16 }}>
        {/* device + name */}
        <div className="form-row" style={{ marginBottom: 0 }}>
          <label className="field">Target device (the THEN device)</label>
          <select
            value={deviceId}
            onChange={(e) => { setDeviceId(e.target.value); dirty(); }}
          >
            {targets.length === 0 && <option value="">No controllable devices</option>}
            {targets.map((d) => (
              <option key={d.id} value={d.id}>{d.name} · {d.room}</option>
            ))}
          </select>
        </div>

        {/* WHEN */}
        <div className="card" style={{ padding: 16, background: "var(--c-surface-2)", boxShadow: "none" }}>
          <div className="row" style={{ marginBottom: 10 }}>
            <Pill kind="blue">WHEN</Pill>
            <span className="muted" style={{ fontSize: 12.5 }}>the trigger condition</span>
          </div>
          <div className="form-row">
            <label className="field">Condition type</label>
            <select value={whenType} onChange={(e) => { setWhenType(e.target.value); dirty(); }}>
              {WHEN_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>

          {whenType === "time" && (
            <>
              <div className="seg" style={{ marginBottom: 12 }}>
                <button className={timeMode === "at" ? "on" : ""} onClick={() => { setTimeMode("at"); dirty(); }}>At</button>
                <button className={timeMode === "between" ? "on" : ""} onClick={() => { setTimeMode("between"); dirty(); }}>Between</button>
              </div>
              {timeMode === "at" ? (
                <div className="form-row" style={{ marginBottom: 0 }}>
                  <label className="field">Time</label>
                  <input type="time" value={timeAt} onChange={(e) => { setTimeAt(e.target.value); dirty(); }} />
                </div>
              ) : (
                <div className="row" style={{ gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <label className="field">From</label>
                    <input type="time" value={timeFrom} onChange={(e) => { setTimeFrom(e.target.value); dirty(); }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label className="field">To</label>
                    <input type="time" value={timeTo} onChange={(e) => { setTimeTo(e.target.value); dirty(); }} />
                  </div>
                </div>
              )}
            </>
          )}

          {whenType === "occupancy" && (
            <div className="stack" style={{ gap: 12 }}>
              <div>
                <label className="field">Sensor</label>
                <select value={occSensor} onChange={(e) => { setOccSensor(e.target.value); dirty(); }}>
                  {sensors.length === 0 && <option value="">No sensors available</option>}
                  {sensors.map((d) => (
                    <option key={d.id} value={d.id}>{d.name} · {d.room}</option>
                  ))}
                </select>
              </div>
              <div className="row" style={{ gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <label className="field">State</label>
                  <select value={occValue} onChange={(e) => { setOccValue(e.target.value); dirty(); }}>
                    <option value="false">empty</option>
                    <option value="true">occupied</option>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label className="field">For (minutes)</label>
                  <input type="number" min={0} value={occMinutes} onChange={(e) => { setOccMinutes(e.target.value); dirty(); }} />
                </div>
              </div>
            </div>
          )}

          {whenType === "day" && (
            <div>
              <label className="field">Days</label>
              <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                {DAYS.map((d) => (
                  <button
                    key={d}
                    className={`btn btn-sm ${dayDays.includes(d) ? "btn-primary" : ""}`}
                    onClick={() => { toggleDay(d); dirty(); }}
                    style={{ textTransform: "capitalize" }}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>
          )}

          {whenType === "device_state" && (
            <div className="stack" style={{ gap: 12 }}>
              <div>
                <label className="field">Device</label>
                <select value={stDevice} onChange={(e) => { setStDevice(e.target.value); dirty(); }}>
                  {devices.map((d) => (
                    <option key={d.id} value={d.id}>{d.name} · {d.room}</option>
                  ))}
                </select>
              </div>
              <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
                <div style={{ flex: 1.4 }}>
                  <label className="field">Control</label>
                  <select value={stControl} onChange={(e) => { setStControl(e.target.value); dirty(); }}>
                    {(stCaps?.controls || []).length === 0 && <option value="">No controls</option>}
                    {(stCaps?.controls || []).map((c) => (
                      <option key={c.name} value={c.name}>{c.label}</option>
                    ))}
                  </select>
                </div>
                <div style={{ width: 80 }}>
                  <label className="field">Op</label>
                  <select value={stOp} onChange={(e) => { setStOp(e.target.value); dirty(); }}>
                    {STATE_OPS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label className="field">Value</label>
                  <ControlValueInput control={stCtrlObj} value={stValue} onChange={(v) => { setStValue(v); dirty(); }} />
                </div>
              </div>
            </div>
          )}

          {whenType === "tariff_window" && (
            <div className="form-row" style={{ marginBottom: 0 }}>
              <label className="field">Window</label>
              <select value={tariffWindow} onChange={(e) => { setTariffWindow(e.target.value); dirty(); }}>
                {TARIFF_WINDOWS.map((w) => <option key={w} value={w}>{w}</option>)}
              </select>
            </div>
          )}
        </div>

        {/* THEN */}
        <div className="card" style={{ padding: 16, background: "var(--c-surface-2)", boxShadow: "none" }}>
          <div className="row" style={{ marginBottom: 10 }}>
            <Pill kind="green">THEN</Pill>
            <span className="muted" style={{ fontSize: 12.5 }}>the action to apply</span>
          </div>
          {!caps && <div className="muted" style={{ fontSize: 13 }}>Loading device controls…</div>}
          {caps && (caps.controls || []).length === 0 && (
            <div className="muted" style={{ fontSize: 13 }}>This device has no controllable features.</div>
          )}
          {caps && (caps.controls || []).length > 0 && (
            <div className="row" style={{ gap: 12, alignItems: "flex-end" }}>
              <div style={{ flex: 1.4 }}>
                <label className="field">Control</label>
                <select
                  value={thenControl}
                  onChange={(e) => {
                    const next = e.target.value;
                    setThenControl(next);
                    const c = (caps.controls || []).find((x) => x.name === next);
                    setThenValue(defaultControlValue(c));
                    dirty();
                  }}
                >
                  {(caps.controls || []).map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.label}{c.safety_sensitive ? " ⚠" : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label className="field">
                  Set to{thenCtrlObj?.unit ? ` (${thenCtrlObj.unit})` : ""}
                </label>
                <ControlValueInput control={thenCtrlObj} value={thenValue} onChange={(v) => { setThenValue(v); dirty(); }} />
              </div>
            </div>
          )}
          {thenCtrlObj?.safety_sensitive && (
            <div style={{ marginTop: 10 }}>
              <Pill kind="orange">⚠ safety-sensitive control</Pill>
            </div>
          )}
        </div>

        {/* name + auto-apply */}
        <div className="form-row" style={{ marginBottom: 0 }}>
          <label className="field">Rule name</label>
          <input
            value={name}
            placeholder="e.g. Turn off living-room AC at night"
            onChange={(e) => { setName(e.target.value); dirty(); }}
          />
        </div>
        <label className="row" style={{ gap: 9, fontSize: 13.5, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={autoApply}
            onChange={(e) => { setAutoApply(e.target.checked); dirty(); }}
            style={{ width: 16 }}
          />
          <span>
            Apply automatically (auto-action)
            <span className="muted" style={{ display: "block", fontSize: 12 }}>
              Off by default — the system will act for you and offer a 2-minute undo (REQ-4.3.6).
            </span>
          </span>
        </label>

        {/* validation result */}
        {validation && (
          <div
            className="card"
            style={{
              padding: 16,
              boxShadow: "none",
              border: `1px solid ${validation.valid ? "rgba(0,158,115,.4)" : "rgba(213,94,0,.4)"}`,
            }}
          >
            <div className="between" style={{ marginBottom: 10 }}>
              <div className="row">
                {validation.valid
                  ? <Pill kind="green">✓ valid</Pill>
                  : <Pill kind="red">✗ has issues</Pill>}
                {validation.summary && (
                  <span className="muted" style={{ fontSize: 13 }}>{validation.summary}</span>
                )}
              </div>
            </div>

            {/* Prominent estimated saving (REQ-4.5.3) */}
            <div className="between" style={{
              background: "rgba(0,158,115,.10)", borderRadius: 10, padding: "10px 14px", marginBottom: 12,
            }}>
              <span className="muted" style={{ fontSize: 13, fontWeight: 600 }}>Estimated saving</span>
              <span style={{ fontSize: 22, fontWeight: 800, color: "var(--ok-green)" }}>
                {vnd(validation.estimated_monthly_saving_vnd)}<span className="muted" style={{ fontSize: 12, fontWeight: 600 }}> / month</span>
              </span>
            </div>

            {validation.errors?.length > 0 && (
              <div className="stack" style={{ gap: 6, marginBottom: 10 }}>
                <span className="field" style={{ marginBottom: 0 }}>Errors</span>
                {validation.errors.map((e, i) => (
                  <div key={i} className="row" style={{ gap: 6, fontSize: 13 }}>
                    <Pill kind="red">error</Pill><span>{e}</span>
                  </div>
                ))}
              </div>
            )}

            {validation.conflicts?.length > 0 && (
              <div className="stack" style={{ gap: 6, marginBottom: 10 }}>
                <span className="field" style={{ marginBottom: 0 }}>Conflicts with existing rules</span>
                {validation.conflicts.map((c, i) => (
                  <div key={i} className="row" style={{ gap: 6, fontSize: 13 }}>
                    <Pill kind="orange">{c.rule_name}</Pill><span className="muted">{c.reason}</span>
                  </div>
                ))}
              </div>
            )}

            {validation.warnings?.length > 0 && (
              <div className="stack" style={{ gap: 6 }}>
                <span className="field" style={{ marginBottom: 0 }}>Safety warnings</span>
                {validation.warnings.map((w, i) => (
                  <div key={i} className="row" style={{ gap: 6, fontSize: 13 }}>
                    <Pill kind="orange">⚠</Pill><span>{w}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="between" style={{ marginTop: 4 }}>
          <button className="btn" onClick={onValidate} disabled={validating || !thenControl}>
            {validating ? "Checking…" : "Check & estimate"}
          </button>
          <div className="row">
            <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button className="btn btn-green" onClick={onSave} disabled={!canSave || saving}>
              {saving ? "Saving…" : "Save rule"}
            </button>
          </div>
        </div>
        {!validation && (
          <div className="muted" style={{ fontSize: 12, textAlign: "right" }}>
            Run “Check &amp; estimate” to see conflicts and the saving before saving.
          </div>
        )}
      </div>
    </Modal>
  );
}

// best initial value for a control
function defaultControlValue(c) {
  if (!c) return null;
  if (c.default != null) return c.default;
  if (c.kind === "toggle") return (c.values && c.values[0]) || "on";
  if (c.kind === "enum") return c.values?.[0] ?? "";
  if (c.kind === "range") return c.min ?? 0;
  return "";
}

// ---- Execution history modal ----------------------------------------------
function HistoryModal({ rule, onClose, onChanged }) {
  const { toast } = useAuth();
  const [rows, setRows] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    api.ruleExecutions(rule.id).then(setRows).catch((err) => toast(err.message, "err"));
  }, [rule.id, toast]);

  useEffect(() => { load(); }, [load]);

  const undo = async (execId) => {
    setBusyId(execId);
    try {
      await api.undoExecution(execId);
      toast("Action undone", "ok");
      load();
      onChanged?.();
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setBusyId(null);
    }
  };

  const describeAction = (a) => {
    if (!a) return "—";
    if (a.control != null) return `${a.control} → ${String(a.value)}`;
    return JSON.stringify(a);
  };
  const canUndo = (r) =>
    r.undo_deadline && !r.undone && new Date(r.undo_deadline).getTime() > Date.now();

  return (
    <Modal title={`History — ${rule.name}`} width={560} onClose={onClose}>
      {rows === null && <Loading />}
      {rows && rows.length === 0 && <Empty>This rule has not run yet.</Empty>}
      {rows && rows.length > 0 && (
        <div className="stack" style={{ gap: 10 }}>
          {rows.map((r) => (
            <div
              key={r.id}
              className="card"
              style={{ padding: 14, boxShadow: "none", background: "var(--c-surface-2)" }}
            >
              <div className="between">
                <span className="tabular" style={{ fontWeight: 600, fontSize: 13.5 }}>
                  {fmtDateTime(r.ts)}
                </span>
                <Pill kind={OUTCOME_KIND[r.outcome] || "gray"}>{r.outcome}</Pill>
              </div>
              <div className="between" style={{ marginTop: 8 }}>
                <span style={{ fontSize: 13.5 }} className="tabular">{describeAction(r.action_json)}</span>
                <span className="row" style={{ gap: 8 }}>
                  <Pill kind="gray">{r.initiator}</Pill>
                  {r.undone && <Pill kind="gray">undone</Pill>}
                  {canUndo(r) && (
                    <button
                      className="btn btn-sm btn-danger"
                      onClick={() => undo(r.id)}
                      disabled={busyId === r.id}
                    >
                      {busyId === r.id ? "Undoing…" : "Undo"}
                    </button>
                  )}
                </span>
              </div>
              {r.detail && (
                <div className="muted" style={{ fontSize: 12, marginTop: 6 }}>{r.detail}</div>
              )}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

// ---- One rule card --------------------------------------------------------
function RuleCard({ rule, deviceMap, onToggle, onAuto, onHistory, onDelete }) {
  const dev = deviceMap[rule.device_id];
  return (
    <div className="card">
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <div className="row" style={{ gap: 8, marginBottom: 4 }}>
            <Icon name={deviceIconName(dev?.type)} size={16} />
            <h2 style={{ fontSize: 15.5 }}>{rule.name}</h2>
          </div>
          <div className="muted" style={{ fontSize: 12.5 }}>
            {dev ? `${dev.name} · ${dev.room}` : `device #${rule.device_id}`}
          </div>
        </div>
        <span
          className="tabular"
          style={{ fontWeight: 800, fontSize: 18, color: "var(--ok-green)", whiteSpace: "nowrap" }}
        >
          {vndShort(rule.estimated_monthly_saving_vnd)}
          <span className="muted" style={{ fontSize: 11, fontWeight: 600 }}>/mo</span>
        </span>
      </div>

      <div
        style={{
          margin: "12px 0",
          padding: "10px 12px",
          background: "var(--c-surface-2)",
          borderRadius: 10,
          borderLeft: `3px solid ${deviceColor(dev?.type)}`,
          fontSize: 13.5,
          lineHeight: 1.5,
        }}
      >
        {rule.summary || "WHEN … THEN …"}
      </div>

      <div className="row" style={{ flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
        {rule.enabled ? <Pill kind="green">enabled</Pill> : <Pill kind="gray">disabled</Pill>}
        {rule.auto_apply && <Pill kind="blue">auto</Pill>}
        {rule.source === "recommendation" && <Pill kind="gray">from recommendation</Pill>}
        {rule.needs_recalculation && <Pill kind="orange">needs recalculation</Pill>}
      </div>

      <div className="between" style={{ flexWrap: "wrap", gap: 10 }}>
        <div className="row" style={{ gap: 14, flexWrap: "wrap" }}>
          <label className="row" style={{ gap: 7, fontSize: 13, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={rule.enabled}
              onChange={(e) => onToggle(rule, e.target.checked)}
              style={{ width: 16 }}
            />
            <span>Enabled</span>
          </label>
          <label className="row" style={{ gap: 7, fontSize: 13, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={rule.auto_apply}
              onChange={(e) => onAuto(rule, e.target.checked)}
              style={{ width: 16 }}
            />
            <span>Auto-apply</span>
          </label>
        </div>
        <div className="row">
          <button className="btn btn-sm" onClick={() => onHistory(rule)}>History</button>
          <button className="btn btn-sm btn-ghost" onClick={() => onDelete(rule)} style={{ color: "var(--ok-vermillion)" }}>
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Page -----------------------------------------------------------------
export default function Rules() {
  const { toast } = useAuth();
  const [rules, setRules] = useState(null);
  const [devices, setDevices] = useState([]);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [historyRule, setHistoryRule] = useState(null);

  const deviceMap = useMemo(() => {
    const m = {};
    for (const d of devices) m[d.id] = d;
    return m;
  }, [devices]);

  const load = useCallback(() => {
    Promise.all([api.rules(), api.devices()])
      .then(([rs, ds]) => { setRules(rs); setDevices(ds); })
      .catch((err) => toast(err.message, "err"));
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  // optimistic patch helper for the two inline toggles
  const patchRule = async (rule, body, okMsg) => {
    try {
      const updated = await api.updateRule(rule.id, body);
      setRules((rs) => rs.map((r) => (r.id === rule.id ? updated : r)));
      toast(okMsg, "ok");
    } catch (err) {
      toast(err.message, "err");
    }
  };

  const onToggle = (rule, enabled) =>
    patchRule(rule, { enabled }, enabled ? "Rule enabled" : "Rule disabled");
  const onAuto = (rule, auto_apply) =>
    patchRule(rule, { auto_apply }, auto_apply ? "Auto-apply on" : "Auto-apply off");

  const onDelete = async (rule) => {
    if (!window.confirm(`Delete “${rule.name}”? Its execution history is kept on the server.`)) return;
    try {
      await api.deleteRule(rule.id);
      setRules((rs) => rs.filter((r) => r.id !== rule.id));
      toast("Rule deleted", "ok");
    } catch (err) {
      toast(err.message, "err");
    }
  };

  if (rules === null) return <Loading />;

  const enabledCount = rules.filter((r) => r.enabled).length;
  const autoCount = rules.filter((r) => r.auto_apply).length;
  const totalSaving = rules
    .filter((r) => r.enabled)
    .reduce((s, r) => s + (r.estimated_monthly_saving_vnd || 0), 0);

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="grid cols-4">
        <BAN label="Active rules" value={enabledCount} accent="blue" icon={<Icon name="sliders" size={20} />}
          sub={`${rules.length} total`} />
        <BAN label="Auto-actions" value={autoCount} accent="orange" icon={<Icon name="bot" size={20} />}
          sub="Apply automatically" />
        <BAN label="Est. monthly saving" value={vndShort(totalSaving)} accent="green" icon={<Icon name="wallet" size={20} />}
          sub="From active rules" />
        <div className="card ban" style={{ justifyContent: "center" }}>
          <button className="btn btn-primary" onClick={() => setBuilderOpen(true)}>
            ＋ New rule
          </button>
          <span className="muted" style={{ fontSize: 12 }}>Build a WHEN-THEN rule</span>
        </div>
      </div>

      {rules.length === 0 ? (
        <div className="card">
          <Empty>
            No rules yet. Create your first WHEN-THEN rule to automate a device and start saving.
            <div style={{ marginTop: 14 }}>
              <button className="btn btn-primary" onClick={() => setBuilderOpen(true)}>＋ New rule</button>
            </div>
          </Empty>
        </div>
      ) : (
        <div className="grid cols-2">
          {rules.map((r) => (
            <RuleCard
              key={r.id}
              rule={r}
              deviceMap={deviceMap}
              onToggle={onToggle}
              onAuto={onAuto}
              onHistory={setHistoryRule}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}

      {builderOpen && (
        <RuleBuilder
          devices={devices}
          onClose={() => setBuilderOpen(false)}
          onSaved={() => { setBuilderOpen(false); load(); }}
        />
      )}
      {historyRule && (
        <HistoryModal
          rule={historyRule}
          onClose={() => setHistoryRule(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}
