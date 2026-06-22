import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import { api } from "../api/client";
import { useLiveFeed } from "../api/ws";
import { BAN, Loading } from "../components/ui";
import { Icon } from "../components/icons";
import { vnd, vndShort, kwh, watts, deviceColor, deviceIconName, OKABE_ITO } from "../lib/format";

export default function Dashboard() {
  const [dash, setDash] = useState(null);
  const [series, setSeries] = useState([]);
  const [top, setTop] = useState([]);
  const [livePower, setLivePower] = useState({}); // device_id -> power_w (instantaneous)

  const load = useCallback(() => {
    api.dashboard().then(setDash).catch(() => {});
    api.consumption("today").then((s) => setSeries(s.points)).catch(() => {});
    api.topConsumers("today").then(setTop).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, [load]);

  useLiveFeed((msg) => {
    if (msg.type === "telemetry" && msg.reading) {
      setLivePower((p) => ({ ...p, [msg.reading.device_id]: msg.reading.power_w }));
    }
  });

  if (!dash) return <Loading />;

  const devices = dash.devices.map((d) => ({
    ...d,
    power_w: livePower[d.device_id] != null && d.online ? livePower[d.device_id] : d.power_w,
  }));
  const liveTotal = devices.filter((d) => d.type !== "sensor" && d.online).reduce((s, d) => s + d.power_w, 0);
  const chart = series.map((p) => ({ t: p.bucket.slice(11, 16) || p.bucket, kwh: p.kwh }));

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="grid cols-4">
        <BAN label="Live power" value={Math.round(liveTotal)} unit="W" accent="blue" icon={<Icon name="bolt" size={20} />}
          sub={`${dash.online_devices}/${dash.total_devices} devices online`} />
        <BAN label="Energy today" value={dash.kwh_today.toFixed(1)} unit="kWh" accent="orange" icon={<Icon name="battery" size={20} />}
          sub={`${kwh(dash.kwh_cycle)} this cycle`} />
        <BAN label="Projected bill" value={vndShort(dash.estimated_bill_vnd)} accent="red" icon={<Icon name="receipt" size={20} />}
          sub={`${dash.tariff_name}`} />
        <BAN label="Saved this cycle" value={vndShort(dash.savings_cycle_vnd)} accent="green" icon={<Icon name="wallet" size={20} />}
          sub="From active saving rules" />
      </div>

      <div className="grid cols-3" style={{ gridTemplateColumns: "2fr 1fr" }}>
        <div className="card">
          <div className="card-title">
            <h2>Today's consumption</h2>
            <span className="muted" style={{ fontSize: 13 }}>{kwh(dash.kwh_today)} · hourly</span>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={chart} margin={{ left: -18, right: 8, top: 6 }}>
              <defs>
                <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={OKABE_ITO.blue} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={OKABE_ITO.blue} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef1f5" />
              <XAxis dataKey="t" tick={{ fontSize: 11, fill: "#8a96a3" }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 11, fill: "#8a96a3" }} width={42} />
              <Tooltip formatter={(v) => [kwh(v, 2), "Energy"]} labelStyle={{ fontWeight: 600 }} />
              <Area type="monotone" dataKey="kwh" stroke={OKABE_ITO.blue} strokeWidth={2} fill="url(#g)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div className="card-title"><h2>Top consumers</h2><span className="muted" style={{ fontSize: 13 }}>today</span></div>
          {top.length === 0 && <div className="empty">No data yet</div>}
          <div className="stack" style={{ gap: 14 }}>
            {top.map((t) => (
              <div key={t.device_id}>
                <div className="between" style={{ fontSize: 13.5, marginBottom: 5 }}>
                  <span className="row" style={{ fontWeight: 600, gap: 7 }}><Icon name={deviceIconName(t.type)} size={15} />{t.name}</span>
                  <span className="tabular muted">{kwh(t.kwh, 2)} · {vndShort(t.cost_vnd)}</span>
                </div>
                <div style={{ background: "#eef1f5", borderRadius: 999, height: 9 }}>
                  <div style={{ width: `${Math.min(100, t.share_pct)}%`, height: 9, borderRadius: 999, background: deviceColor(t.type) }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <h2>Live devices</h2>
          <Link to="/devices" className="btn btn-sm">Manage devices →</Link>
        </div>
        <div className="grid cols-4">
          {devices.map((d) => (
            <div key={d.device_id} className="card" style={{ padding: 16, boxShadow: "none", background: "var(--c-surface-2)" }}>
              <div className="between">
                <Icon name={deviceIconName(d.type)} size={22} />
                <span className="row" style={{ gap: 6, fontSize: 12 }}>
                  <span className={`dot ${d.online ? "dot-on" : "dot-off"}`} />
                  {d.online ? "online" : "offline"}
                </span>
              </div>
              <div style={{ fontWeight: 600, marginTop: 8, fontSize: 14 }}>{d.name}</div>
              <div className="muted" style={{ fontSize: 12 }}>{d.room}</div>
              <div className="between" style={{ marginTop: 10 }}>
                <span className="tabular" style={{ fontSize: 20, fontWeight: 800, color: deviceColor(d.type) }}>
                  {d.type === "sensor" ? (d.temperature?.toFixed(1) ?? "—") + "°C" : watts(d.power_w)}
                </span>
                <span className="muted tabular" style={{ fontSize: 12 }}>{kwh(d.kwh_today, 2)} today</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
