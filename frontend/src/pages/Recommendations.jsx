// Explainable habit recommendations (REQ-4.4.1..4.4.5).
//
// Every card leads with the green VND/month saving (the value is the hero), then
// shows the WHEN→THEN summary, a human-readable rationale, and the exact data
// window the miner used (REQ-4.4.2). Accept turns a recommendation into a rule
// (REQ-4.4.4); Dismiss hides it for ~30 days (REQ-4.4.5).
import { useEffect, useState, useCallback } from "react";
import { api } from "../api/client";
import { Modal, Loading, Empty, Pill } from "../components/ui";
import { vnd, fmtDateTime } from "../lib/format";
import { useAuth } from "../auth/AuthContext";

export default function Recommendations() {
  const { toast } = useAuth();
  const [recs, setRecs] = useState(null); // null = first load
  const [analyzing, setAnalyzing] = useState(false);
  const [busy, setBusy] = useState(null); // rec id currently mutating
  const [accepting, setAccepting] = useState(null); // rec being accepted (modal)
  const [acceptName, setAcceptName] = useState("");
  const [autoApply, setAutoApply] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api.recommendations().then(setRecs).catch((err) => {
      toast(err.message, "err");
      setRecs([]);
    });
  }, [toast]);

  useEffect(() => {
    load();
  }, [load]);

  const analyze = async () => {
    setAnalyzing(true);
    try {
      const fresh = await api.analyzeRecommendations();
      setRecs(fresh);
      toast(
        fresh.length
          ? `Found ${fresh.length} recommendation${fresh.length > 1 ? "s" : ""}`
          : "No new habits found yet — keep collecting telemetry",
        "ok"
      );
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setAnalyzing(false);
    }
  };

  const openAccept = (rec) => {
    setAccepting(rec);
    setAcceptName(rec.title || "");
    setAutoApply(false);
  };

  const confirmAccept = async () => {
    if (!accepting) return;
    setSaving(true);
    try {
      await api.acceptRecommendation(accepting.id, {
        name: acceptName.trim() || accepting.title,
        auto_apply: autoApply,
      });
      toast("Saved as a rule", "ok");
      setAccepting(null);
      load();
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setSaving(false);
    }
  };

  const dismiss = async (rec) => {
    setBusy(rec.id);
    try {
      await api.dismissRecommendation(rec.id);
      toast("Dismissed — hidden for ~30 days", "ok");
      load();
    } catch (err) {
      toast(err.message, "err");
    } finally {
      setBusy(null);
    }
  };

  if (recs === null) return <Loading />;

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="between">
        <div>
          <h1 style={{ fontSize: 22 }}>Recommendations</h1>
          <div className="muted" style={{ fontSize: 13.5, marginTop: 4 }}>
            Explainable habit suggestions, ranked by estimated monthly saving.
          </div>
        </div>
        <button className="btn btn-primary" onClick={analyze} disabled={analyzing}>
          {analyzing ? "Analyzing…" : "🔍 Analyze my usage"}
        </button>
      </div>

      {recs.length === 0 ? (
        <div className="card">
          <Empty>
            <div style={{ fontSize: 38, marginBottom: 10 }}>💡</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "var(--c-text)" }}>
              No recommendations yet
            </div>
            <div style={{ maxWidth: 440, margin: "10px auto 0", fontSize: 13.5, lineHeight: 1.6 }}>
              The habit miner needs at least <strong>7 days of telemetry</strong> to spot
              repeatable patterns worth automating. Once you have enough history, click
              <strong> "Analyze my usage"</strong> above to generate explainable suggestions.
            </div>
            <button
              className="btn btn-primary"
              style={{ marginTop: 18 }}
              onClick={analyze}
              disabled={analyzing}
            >
              {analyzing ? "Analyzing…" : "🔍 Analyze my usage"}
            </button>
          </Empty>
        </div>
      ) : (
        <div className="grid cols-2">
          {recs.map((rec, i) => (
            <RecCard
              key={rec.id}
              rec={rec}
              rank={i + 1}
              busy={busy === rec.id}
              onAccept={() => openAccept(rec)}
              onDismiss={() => dismiss(rec)}
            />
          ))}
        </div>
      )}

      {accepting && (
        <Modal
          title="Accept recommendation"
          width={480}
          onClose={() => (saving ? null : setAccepting(null))}
          footer={
            <>
              <button className="btn btn-ghost" onClick={() => setAccepting(null)} disabled={saving}>
                Cancel
              </button>
              <button className="btn btn-green" onClick={confirmAccept} disabled={saving}>
                {saving ? "Saving…" : "Create rule"}
              </button>
            </>
          }
        >
          <div className="muted" style={{ fontSize: 13, marginBottom: 16, lineHeight: 1.55 }}>
            This turns the suggestion into a saving rule you can manage on the Rules page.
            <br />
            <span style={{ fontWeight: 600, color: "var(--c-text)" }}>{accepting.summary}</span>
          </div>

          <div className="form-row">
            <label className="field" htmlFor="rec-name">Rule name</label>
            <input
              id="rec-name"
              type="text"
              value={acceptName}
              onChange={(e) => setAcceptName(e.target.value)}
              placeholder={accepting.title}
            />
          </div>

          <label
            className="row"
            style={{ gap: 10, cursor: "pointer", alignItems: "flex-start", marginTop: 4 }}
          >
            <input
              type="checkbox"
              checked={autoApply}
              onChange={(e) => setAutoApply(e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              <span style={{ fontWeight: 600, fontSize: 13.5 }}>Apply automatically (auto-action)</span>
              <div className="muted" style={{ fontSize: 12.5, marginTop: 2, lineHeight: 1.5 }}>
                When on, the rule acts on your devices on its own. Leave off to be asked first.
              </div>
            </span>
          </label>
        </Modal>
      )}
    </div>
  );
}

function RecCard({ rec, rank, busy, onAccept, onDismiss }) {
  return (
    <div className="card stack" style={{ gap: 14 }}>
      <div className="between" style={{ alignItems: "flex-start" }}>
        <div className="row" style={{ gap: 8 }}>
          <Pill kind="gray">#{rank}</Pill>
          <h2 style={{ fontSize: 16 }}>{rec.title}</h2>
        </div>
        <Pill kind="blue">suggested</Pill>
      </div>

      {/* Green VND saving is the visual hero */}
      <div
        style={{
          background: "rgba(0,158,115,.10)",
          borderRadius: 12,
          padding: "14px 16px",
        }}
      >
        <div
          className="muted"
          style={{
            fontSize: 11.5,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: ".04em",
          }}
        >
          Est. saving / month
        </div>
        <div
          className="tabular"
          style={{ fontSize: 32, fontWeight: 800, lineHeight: 1.05, color: "var(--c-savings)" }}
        >
          {vnd(rec.estimated_monthly_saving_vnd)}
        </div>
      </div>

      {/* WHEN → THEN summary */}
      {rec.summary && (
        <div
          style={{
            fontSize: 14,
            fontWeight: 600,
            lineHeight: 1.5,
            borderLeft: "3px solid var(--ok-blue)",
            paddingLeft: 12,
          }}
        >
          {rec.summary}
        </div>
      )}

      {/* Human-readable rationale */}
      {rec.rationale && (
        <p className="muted" style={{ fontSize: 13, lineHeight: 1.6, margin: 0 }}>
          {rec.rationale}
        </p>
      )}

      {/* Data window used (REQ-4.4.2) */}
      <div className="muted" style={{ fontSize: 12 }}>
        📅 Based on data from {fmtDateTime(rec.data_window_start)} – {fmtDateTime(rec.data_window_end)}
      </div>

      <div className="row" style={{ gap: 10, marginTop: 2 }}>
        <button className="btn btn-green btn-sm" onClick={onAccept} disabled={busy}>
          ✓ Accept
        </button>
        <button className="btn btn-sm" onClick={onDismiss} disabled={busy}>
          {busy ? "…" : "Dismiss"}
        </button>
      </div>
    </div>
  );
}
