// Settings page — tariff config, residents, preferences.
// Covers: Business Rule (manual tariff config), NFR-SEC RBAC (administrator-only mutations),
// SRS 6.2 localization (locale preference). Non-administrators get a read-only view.
import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import { BAN, Pill, Modal, Loading, Empty } from "../components/ui";
import { Icon } from "../components/icons";
import { vnd } from "../lib/format";
import { useAuth } from "../auth/AuthContext";

const TARIFF_TYPE_LABEL = { flat: "Flat rate", tiered: "Tiered", tou: "Time-of-use" };
const TARIFF_KIND = { flat: "blue", tiered: "orange", tou: "purple" };

// Compact, human-readable summary of a tariff's config for the card body.
function tariffSummary(t) {
  const c = t.config || {};
  if (t.type === "flat") {
    return c.price != null ? `${vnd(c.price)} / kWh` : "Flat price not set";
  }
  if (t.type === "tiered") {
    const tiers = c.tiers || [];
    if (!tiers.length) return "No tiers configured";
    return `${tiers.length} tier${tiers.length > 1 ? "s" : ""} · from ${vnd(tiers[0].price)}/kWh`;
  }
  if (t.type === "tou") {
    const w = c.windows || [];
    return `Default ${vnd(c.default_price)}/kWh · ${w.length} window${w.length === 1 ? "" : "s"}`;
  }
  return "—";
}

export default function Settings() {
  const { user, toast } = useAuth();
  const isAdmin = user?.role === "admin";

  const [settings, setSettings] = useState(null);
  const [tariffs, setTariffs] = useState([]);
  const [loaded, setLoaded] = useState(false);

  const [busyTariff, setBusyTariff] = useState(null);
  const [showTariffModal, setShowTariffModal] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([
        api.settings(),
        api.tariffs().catch(() => []),
      ]);
      setSettings(s);
      setTariffs(t || []);
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setLoaded(true);
    }
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const activate = async (id) => {
    setBusyTariff(id);
    try {
      await api.activateTariff(id);
      toast("Tariff activated", "ok");
      await load();
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setBusyTariff(null);
    }
  };

  if (!loaded) return <Loading />;
  if (!settings) return <Empty>Could not load settings.</Empty>;

  const activeTariff = settings.active_tariff;

  return (
    <div className="stack" style={{ gap: 20 }}>
      {/* ---- Overview BANs ---- */}
      <div className="grid cols-4">
        <BAN
          label={settings.home_id == null ? "Building" : "Unit"}
          value={settings.home_name}
          accent="blue"
          icon={<Icon name="home" size={20} />}
          sub={settings.home_id == null ? "All units (building owner)" : `Unit #${settings.home_id}`}
        />
        <BAN
          label="Billing cycle day"
          value={settings.billing_cycle_day}
          accent="orange"
          icon={<Icon name="calendar" size={20} />}
          sub="Day of month meter resets"
        />
        <BAN
          label="Currency"
          value={settings.currency}
          accent="green"
          icon={<Icon name="currency" size={20} />}
          sub={`Locale ${settings.locale}`}
        />
        <BAN
          label="Active tariff"
          value={activeTariff ? activeTariff.name : "None"}
          accent="red"
          icon={<Icon name="receipt" size={20} />}
          sub={activeTariff ? TARIFF_TYPE_LABEL[activeTariff.type] || activeTariff.type : "No tariff set"}
        />
      </div>

      {/* ---- Signed-in user + role note ---- */}
      <div className="card">
        <div className="card-title">
          <h2>Signed in</h2>
          {isAdmin ? (
            <Pill kind="green">administrator · full access</Pill>
          ) : (
            <Pill kind="gray">{user?.role} · read-only</Pill>
          )}
        </div>
        <div className="between" style={{ flexWrap: "wrap", gap: 14 }}>
          <div className="row" style={{ gap: 14 }}>
            <div
              className="ban-ico"
              style={{ background: "rgba(0,114,178,.12)", marginBottom: 0 }}
            >
              <Icon name="user" size={20} />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15 }}>{user?.full_name}</div>
              <div className="muted" style={{ fontSize: 13 }}>{user?.email}</div>
            </div>
          </div>
          {!isAdmin && (
            <div className="muted" style={{ fontSize: 13, maxWidth: 420 }}>
              Only the <strong>Administrator</strong> can change the tariff or manage residents
              (role-based access control).
            </div>
          )}
        </div>
      </div>

      {/* ---- Tariffs ---- */}
      <div className="card">
        <div className="card-title">
          <h2>Electricity tariffs</h2>
          {isAdmin ? (
            <button className="btn btn-sm btn-primary" onClick={() => setShowTariffModal(true)}>
              ＋ Add tariff
            </button>
          ) : (
            <span className="muted" style={{ fontSize: 13 }}>Administrator-managed</span>
          )}
        </div>

        {tariffs.length === 0 ? (
          <Empty>No tariffs configured yet.</Empty>
        ) : (
          <div className="grid cols-3">
            {tariffs.map((t) => (
              <div
                key={t.id}
                className="card"
                style={{
                  padding: 16,
                  boxShadow: "none",
                  background: "var(--c-surface-2)",
                  borderColor: t.active ? "var(--ok-green)" : "var(--c-border)",
                }}
              >
                <div className="between">
                  <Pill kind={TARIFF_KIND[t.type] || "gray"}>
                    {TARIFF_TYPE_LABEL[t.type] || t.type}
                  </Pill>
                  {t.active && <Pill kind="green">active</Pill>}
                </div>
                <div style={{ fontWeight: 700, marginTop: 10, fontSize: 15 }}>{t.name}</div>
                <div className="muted" style={{ fontSize: 12.5, marginTop: 4, minHeight: 32 }}>
                  {tariffSummary(t)}
                </div>
                <div className="muted tabular" style={{ fontSize: 11.5, marginTop: 2 }}>
                  {t.currency}
                </div>
                {isAdmin && (
                  <div style={{ marginTop: 12 }}>
                    <button
                      className="btn btn-sm btn-green"
                      disabled={t.active || busyTariff === t.id}
                      onClick={() => activate(t.id)}
                    >
                      {t.active ? "Active" : busyTariff === t.id ? "Activating…" : "Activate"}
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ---- Residents (administrator only) ---- */}
      {isAdmin && <Residents toast={toast} />}

      {showTariffModal && (
        <AddTariffModal
          onClose={() => setShowTariffModal(false)}
          onCreated={async () => {
            setShowTariffModal(false);
            await load();
          }}
          toast={toast}
        />
      )}
    </div>
  );
}

/* ============================ Residents ============================ */

function Residents({ toast }) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [unitName, setUnitName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setEmail("");
    setFullName("");
    setPassword("");
    setUnitName("");
  };

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.addResident({
        email,
        full_name: fullName,
        password,
        unit_name: unitName,
      });
      toast("Unit sold — resident onboarded with the default device package", "ok");
      reset();
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="card">
      <div className="card-title">
        <h2>Sell a unit / onboard a resident</h2>
        <span className="muted" style={{ fontSize: 13 }}>Administrator-managed access</span>
      </div>
      <div className="muted" style={{ fontSize: 12.5, marginBottom: 12 }}>
        Creating a resident provisions a new <strong>unit</strong> pre-fitted with the standard
        smart-device package; the resident controls every operable device in their own unit.
      </div>
      <form onSubmit={submit}>
        <div className="grid cols-4">
          <div className="form-row">
            <label className="field">Unit name</label>
            <input
              type="text"
              required
              value={unitName}
              onChange={(e) => setUnitName(e.target.value)}
              placeholder="Unit 204"
            />
          </div>
          <div className="form-row">
            <label className="field">Resident email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="member@home.vn"
            />
          </div>
          <div className="form-row">
            <label className="field">Full name</label>
            <input
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Nguyễn Văn A"
            />
          </div>
          <div className="form-row">
            <label className="field">Temporary password</label>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 6 characters"
            />
          </div>
        </div>

        <div className="row" style={{ justifyContent: "flex-end", marginTop: 6 }}>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting ? "Onboarding…" : "Sell unit & onboard"}
          </button>
        </div>
      </form>
    </div>
  );
}

/* ============================ Add tariff modal ============================ */

const emptyTier = () => ({ up_to_kwh: "", price: "" });
const emptyWindow = () => ({ name: "", start: "", end: "", price: "" });

function AddTariffModal({ onClose, onCreated, toast }) {
  const [name, setName] = useState("");
  const [type, setType] = useState("flat");
  const [submitting, setSubmitting] = useState(false);

  // flat
  const [price, setPrice] = useState("");
  // tiered
  const [tiers, setTiers] = useState([
    { up_to_kwh: "50", price: "" },
    emptyTier(), // last row: unlimited
  ]);
  // tou
  const [defaultPrice, setDefaultPrice] = useState("");
  const [windows, setWindows] = useState([
    { name: "Peak", start: "09:30", end: "11:30", price: "" },
    { name: "Off-peak", start: "22:00", end: "04:00", price: "" },
  ]);

  const setTier = (i, key, val) =>
    setTiers((cur) => cur.map((t, idx) => (idx === i ? { ...t, [key]: val } : t)));
  const setWindow = (i, key, val) =>
    setWindows((cur) => cur.map((w, idx) => (idx === i ? { ...w, [key]: val } : w)));

  const buildConfig = () => {
    if (type === "flat") {
      return { price: Number(price) };
    }
    if (type === "tiered") {
      return {
        tiers: tiers.map((t) => ({
          up_to_kwh: t.up_to_kwh === "" ? null : Number(t.up_to_kwh),
          price: Number(t.price),
        })),
      };
    }
    // tou
    return {
      default_price: Number(defaultPrice),
      windows: windows.map((w) => ({
        name: w.name,
        start: w.start,
        end: w.end,
        price: Number(w.price),
      })),
    };
  };

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.createTariff({
        name,
        type,
        config: buildConfig(),
        currency: "VND",
      });
      toast("Tariff created & activated", "ok");
      await onCreated();
    } catch (err) {
      toast(err.message, "err");
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="Add tariff"
      onClose={onClose}
      width={560}
      footer={
        <>
          <button className="btn" onClick={onClose} type="button">Cancel</button>
          <button
            className="btn btn-primary"
            type="submit"
            form="tariff-form"
            disabled={submitting}
          >
            {submitting ? "Saving…" : "Create tariff"}
          </button>
        </>
      }
    >
      <form id="tariff-form" onSubmit={submit}>
        <div className="form-row">
          <label className="field">Tariff name</label>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="EVN bậc thang 2024"
          />
        </div>

        <div className="form-row">
          <label className="field">Type</label>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="flat">Flat rate</option>
            <option value="tiered">Tiered (bậc thang)</option>
            <option value="tou">Time-of-use (peak hours)</option>
          </select>
        </div>

        {/* ---- FLAT ---- */}
        {type === "flat" && (
          <div className="form-row">
            <label className="field">Price (VND / kWh)</label>
            <input
              type="number"
              min="0"
              step="any"
              required
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              placeholder="2500"
            />
          </div>
        )}

        {/* ---- TIERED ---- */}
        {type === "tiered" && (
          <div className="form-row">
            <label className="field">
              Tiers — leave the last “up to” blank for the unlimited final tier
            </label>
            <div className="stack" style={{ gap: 8 }}>
              {tiers.map((t, i) => {
                const isLast = i === tiers.length - 1;
                return (
                  <div className="row" key={i} style={{ gap: 8 }}>
                    <div style={{ flex: 1 }}>
                      <input
                        type="number"
                        min="0"
                        step="any"
                        value={t.up_to_kwh}
                        onChange={(e) => setTier(i, "up_to_kwh", e.target.value)}
                        placeholder={isLast ? "∞ (unlimited)" : "up to kWh"}
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <input
                        type="number"
                        min="0"
                        step="any"
                        required
                        value={t.price}
                        onChange={(e) => setTier(i, "price", e.target.value)}
                        placeholder="VND / kWh"
                      />
                    </div>
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      disabled={tiers.length <= 1}
                      onClick={() => setTiers((cur) => cur.filter((_, idx) => idx !== i))}
                      title="Remove tier"
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>
            <button
              type="button"
              className="btn btn-sm"
              style={{ marginTop: 10 }}
              onClick={() => setTiers((cur) => [...cur, emptyTier()])}
            >
              ＋ Add tier
            </button>
          </div>
        )}

        {/* ---- TOU ---- */}
        {type === "tou" && (
          <>
            <div className="form-row">
              <label className="field">Default price (VND / kWh)</label>
              <input
                type="number"
                min="0"
                step="any"
                required
                value={defaultPrice}
                onChange={(e) => setDefaultPrice(e.target.value)}
                placeholder="2500"
              />
            </div>
            <div className="form-row">
              <label className="field">Time-of-use windows</label>
              <div className="stack" style={{ gap: 8 }}>
                {windows.map((w, i) => (
                  <div className="row" key={i} style={{ gap: 8 }}>
                    <div style={{ flex: 1.2 }}>
                      <input
                        value={w.name}
                        onChange={(e) => setWindow(i, "name", e.target.value)}
                        placeholder="name"
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <input
                        type="time"
                        value={w.start}
                        onChange={(e) => setWindow(i, "start", e.target.value)}
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <input
                        type="time"
                        value={w.end}
                        onChange={(e) => setWindow(i, "end", e.target.value)}
                      />
                    </div>
                    <div style={{ flex: 1 }}>
                      <input
                        type="number"
                        min="0"
                        step="any"
                        required
                        value={w.price}
                        onChange={(e) => setWindow(i, "price", e.target.value)}
                        placeholder="VND/kWh"
                      />
                    </div>
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      disabled={windows.length <= 1}
                      onClick={() => setWindows((cur) => cur.filter((_, idx) => idx !== i))}
                      title="Remove window"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="btn btn-sm"
                style={{ marginTop: 10 }}
                onClick={() => setWindows((cur) => [...cur, emptyWindow()])}
              >
                ＋ Add window
              </button>
            </div>
          </>
        )}
      </form>
    </Modal>
  );
}
