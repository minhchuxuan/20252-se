// Reports page — consumption history, top consumers, savings & CSV export.
// Covers REQ-4.1.2 (consumption history), REQ-4.1.5 (top consumers) and
// Other Requirements 6.1 (CSV export). Visual language matches Dashboard.jsx.
import { useCallback, useEffect, useState } from "react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from "recharts";
import { api, downloadCsv } from "../api/client";
import { BAN, Pill, Loading, Empty } from "../components/ui";
import { Icon } from "../components/icons";
import { useAuth } from "../auth/AuthContext";
import {
  vnd, vndShort, kwh, fmtDateTime, deviceColor, deviceIconName, OKABE_ITO,
} from "../lib/format";

const RANGES = [
  { key: "today", label: "Today" },
  { key: "week", label: "Week" },
  { key: "month", label: "Month" },
];

// Bucket label: "today" buckets are hourly ISO datetimes (HH:MM),
// week/month buckets are daily ISO dates (MM-DD).
function bucketLabel(bucket, granularity) {
  if (granularity === "hour") return bucket.slice(11, 16) || bucket;
  return bucket.slice(5) || bucket;
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload;
  return (
    <div className="card" style={{ padding: "10px 13px", boxShadow: "var(--shadow)" }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{p.label}</div>
      <div className="tabular" style={{ fontSize: 13 }}>{kwh(p.kwh, 2)}</div>
      <div className="tabular muted" style={{ fontSize: 12.5 }}>{vnd(p.cost_vnd)}</div>
    </div>
  );
}

export default function Reports() {
  const { toast } = useAuth();
  const [range, setRange] = useState("today");
  const [series, setSeries] = useState(null);     // ConsumptionSeries
  const [top, setTop] = useState([]);             // TopConsumer[]
  const [summary, setSummary] = useState(null);   // SavingsSummary
  const [records, setRecords] = useState([]);     // SavingsRecordOut[]
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(null);

  // Re-fetch range-scoped data whenever the segmented control changes.
  const loadRange = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.consumption(range).catch(() => null),
      api.topConsumers(range, 5).catch(() => []),
    ])
      .then(([s, t]) => {
        setSeries(s);
        setTop(Array.isArray(t) ? t : []);
      })
      .finally(() => setLoading(false));
  }, [range]);

  // Range-independent rollups (savings) — loaded once.
  useEffect(() => {
    api.savingsSummary().then(setSummary).catch(() => {});
    api.savingsRecords().then((r) => setRecords(Array.isArray(r) ? r : [])).catch(() => {});
  }, []);

  useEffect(() => { loadRange(); }, [loadRange]);

  const runExport = async (kind, filename, key) => {
    setExporting(key);
    try {
      await downloadCsv(kind, filename);
      toast(`Exported ${filename}`, "ok");
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setExporting(null);
    }
  };

  if (loading && !series) return <Loading />;

  const points = series?.points || [];
  const granularity = series?.granularity || "hour";
  const chart = points.map((p) => ({
    label: bucketLabel(p.bucket, granularity),
    kwh: p.kwh,
    cost_vnd: p.cost_vnd,
  }));
  const peak = chart.reduce((m, c) => Math.max(m, c.kwh), 0);

  // Savings record rollups. Measured saving is a ledger of actual accrued savings;
  // the estimate is a forward-looking property of the enabled rules, so it comes from
  // the savings summary (sum of the enabled rules' monthly estimates), not from a
  // ledger record -- the backend never writes an "estimate" SavingsRecord.
  const measured = records.filter((r) => r.kind === "measured");
  const measuredSaved = measured.reduce((s, r) => s + (r.saved_vnd || 0), 0);
  const estimateSaved = summary?.estimated_saved_vnd_month || 0;
  const totalSaved = records.reduce((s, r) => s + (r.saved_vnd || 0), 0);
  const recentRecords = [...records]
    .sort((a, b) => new Date(b.period_end) - new Date(a.period_end))
    .slice(0, 4);
  const recPeak = recentRecords.reduce((m, r) => Math.max(m, Math.abs(r.saved_vnd || 0)), 0);

  return (
    <div className="stack" style={{ gap: 20 }}>
      {/* Range selector */}
      <div className="between">
        <div className="seg">
          {RANGES.map((r) => (
            <button
              key={r.key}
              className={range === r.key ? "on" : ""}
              onClick={() => setRange(r.key)}
            >
              {r.label}
            </button>
          ))}
        </div>
        <span className="muted" style={{ fontSize: 13 }}>
          {granularity === "hour" ? "hourly buckets" : "daily buckets"}
        </span>
      </div>

      {/* BAN row */}
      <div className="grid cols-3">
        <BAN
          label="Energy used"
          value={(series?.total_kwh ?? 0).toFixed(1)}
          unit="kWh"
          accent="blue"
          icon={<Icon name="battery" size={20} />}
          sub={`over the selected ${range}`}
        />
        <BAN
          label="Cost"
          value={vndShort(series?.total_cost_vnd ?? 0)}
          accent="red"
          icon={<Icon name="receipt" size={20} />}
          sub={`${vnd(series?.total_cost_vnd ?? 0)} total`}
        />
        <BAN
          label="Saved this cycle"
          value={vndShort(summary?.saved_vnd_cycle ?? 0)}
          accent="green"
          icon={<Icon name="wallet" size={20} />}
          sub={summary ? `${kwh(summary.saved_kwh_cycle, 1)} avoided` : "—"}
        />
      </div>

      {/* Consumption history chart */}
      <div className="card">
        <div className="card-title">
          <h2>Consumption history</h2>
          <span className="muted" style={{ fontSize: 13 }}>
            {kwh(series?.total_kwh ?? 0)} · {granularity === "hour" ? "by hour" : "by day"}
          </span>
        </div>
        {chart.length === 0 ? (
          <Empty>No consumption recorded for this range yet.</Empty>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={chart} margin={{ left: -16, right: 8, top: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eef1f5" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11, fill: "#8a96a3" }}
                interval="preserveStartEnd"
              />
              <YAxis tick={{ fontSize: 11, fill: "#8a96a3" }} width={42} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(0,114,178,.06)" }} />
              <Bar dataKey="kwh" radius={[4, 4, 0, 0]} maxBarSize={46}>
                {chart.map((c, i) => (
                  <Cell
                    key={i}
                    fill={OKABE_ITO.blue}
                    fillOpacity={peak > 0 && c.kwh >= peak ? 1 : 0.8}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="grid cols-2">
        {/* Top consumers (REQ-4.1.5) */}
        <div className="card">
          <div className="card-title">
            <h2>Top consumers</h2>
            <span className="muted" style={{ fontSize: 13 }}>{range}</span>
          </div>
          {top.length === 0 ? (
            <Empty>No device usage in this range.</Empty>
          ) : (
            <div className="stack" style={{ gap: 14 }}>
              {top.map((t) => (
                <div key={t.device_id}>
                  <div className="between" style={{ fontSize: 13.5, marginBottom: 5 }}>
                    <span className="row" style={{ fontWeight: 600, gap: 7 }}><Icon name={deviceIconName(t.type)} size={15} />{t.name}</span>
                    <span className="tabular muted">
                      {kwh(t.kwh, 2)} · {vndShort(t.cost_vnd)}
                    </span>
                  </div>
                  <div style={{ background: "#eef1f5", borderRadius: 999, height: 9 }}>
                    <div
                      style={{
                        width: `${Math.max(2, Math.min(100, t.share_pct))}%`,
                        height: 9,
                        borderRadius: 999,
                        background: deviceColor(t.type),
                      }}
                    />
                  </div>
                  <div className="muted tabular" style={{ fontSize: 11.5, marginTop: 3 }}>
                    {(t.share_pct ?? 0).toFixed(0)}% of usage
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Savings records — measured vs estimate */}
        <div className="card">
          <div className="card-title">
            <h2>Savings ledger</h2>
            <span className="tabular muted" style={{ fontSize: 13 }}>{vnd(totalSaved)} total</span>
          </div>
          {records.length === 0 ? (
            <Empty>No savings recorded yet. Activate saving rules to start.</Empty>
          ) : (
            <div className="stack" style={{ gap: 16 }}>
              <div className="grid cols-2" style={{ gap: 12 }}>
                <div className="card" style={{ padding: 14, boxShadow: "none", background: "var(--c-surface-2)" }}>
                  <div className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Measured</div>
                  <div className="tabular" style={{ fontSize: 20, fontWeight: 800, color: OKABE_ITO.green }}>
                    {vndShort(measuredSaved)}
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>{measured.length} records</div>
                </div>
                <div className="card" style={{ padding: 14, boxShadow: "none", background: "var(--c-surface-2)" }}>
                  <div className="muted" style={{ fontSize: 12, fontWeight: 600 }}>Estimated</div>
                  <div className="tabular" style={{ fontSize: 20, fontWeight: 800, color: OKABE_ITO.orange }}>
                    {vndShort(estimateSaved)}
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>forecast / month</div>
                </div>
              </div>

              <div className="stack" style={{ gap: 11 }}>
                {recentRecords.map((r) => (
                  <div key={r.id}>
                    <div className="between" style={{ fontSize: 13, marginBottom: 4 }}>
                      <span className="row" style={{ gap: 8 }}>
                        <Pill kind={r.kind === "measured" ? "green" : "orange"}>{r.kind}</Pill>
                        <span className="muted tabular">{fmtDateTime(r.period_end)}</span>
                      </span>
                      <span className="tabular" style={{ fontWeight: 700, color: OKABE_ITO.green }}>
                        {vndShort(r.saved_vnd)}
                      </span>
                    </div>
                    <div style={{ background: "#eef1f5", borderRadius: 999, height: 7 }}>
                      <div
                        style={{
                          width: `${recPeak > 0 ? Math.max(3, Math.min(100, (Math.abs(r.saved_vnd) / recPeak) * 100)) : 0}%`,
                          height: 7,
                          borderRadius: 999,
                          background: r.kind === "measured" ? OKABE_ITO.green : OKABE_ITO.orange,
                        }}
                      />
                    </div>
                    <div className="muted tabular" style={{ fontSize: 11.5, marginTop: 3 }}>
                      {kwh(r.saved_kwh, 2)} avoided · baseline {kwh(r.baseline_kwh, 1)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* CSV export (Other Requirements 6.1) */}
      <div className="card">
        <div className="card-title">
          <h2>Export data</h2>
          <span className="muted" style={{ fontSize: 13 }}>Download as CSV</span>
        </div>
        <div className="grid cols-3">
          <div className="card" style={{ padding: 16, boxShadow: "none", background: "var(--c-surface-2)" }}>
            <div className="row" style={{ fontWeight: 700, fontSize: 14, gap: 8 }}><Icon name="trending" size={16} />Readings</div>
            <div className="muted" style={{ fontSize: 12.5, margin: "5px 0 12px" }}>
              Raw device readings, last 30 days.
            </div>
            <button
              className="btn btn-primary btn-sm"
              disabled={exporting === "readings"}
              onClick={() => runExport("readings.csv?days=30", "readings.csv", "readings")}
            >
              {exporting === "readings" ? "Exporting…" : "Download CSV"}
            </button>
          </div>

          <div className="card" style={{ padding: 16, boxShadow: "none", background: "var(--c-surface-2)" }}>
            <div className="row" style={{ fontWeight: 700, fontSize: 14, gap: 8 }}><Icon name="sliders" size={16} />Automation rules</div>
            <div className="muted" style={{ fontSize: 12.5, margin: "5px 0 12px" }}>
              All saving & automation rules.
            </div>
            <button
              className="btn btn-primary btn-sm"
              disabled={exporting === "rules"}
              onClick={() => runExport("rules.csv", "rules.csv", "rules")}
            >
              {exporting === "rules" ? "Exporting…" : "Download CSV"}
            </button>
          </div>

          <div className="card" style={{ padding: 16, boxShadow: "none", background: "var(--c-surface-2)" }}>
            <div className="row" style={{ fontWeight: 700, fontSize: 14, gap: 8 }}><Icon name="wallet" size={16} />Savings</div>
            <div className="muted" style={{ fontSize: 12.5, margin: "5px 0 12px" }}>
              Measured & estimated savings ledger.
            </div>
            <button
              className="btn btn-primary btn-sm"
              disabled={exporting === "savings"}
              onClick={() => runExport("savings.csv", "savings.csv", "savings")}
            >
              {exporting === "savings" ? "Exporting…" : "Download CSV"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
