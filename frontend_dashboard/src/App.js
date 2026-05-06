import React, { useState, useEffect } from "react";
import useMachineStream from "./useMachineStream";

import MachineCard from "./components/MachineCard";
import FactoryTwin3D from "./components/FactoryTwin3D";
import TemperatureChart from "./components/TemperatureChart";
import AlertPanel from "./components/AlertPanel";
import Chatbot from "./components/Chatbot";

function App() {

  const {
    machines = {},
    factoryAnalytics = {},
    agentAlerts = [],
    agentActions = [],
    popupMessage
  } = useMachineStream();

  const [showChatbot, setShowChatbot] = useState(false);
  const [timeRange, setTimeRange] = useState(5);

  // collapsible panel state — all three start closed for a clean dashboard
  const [openRecent, setOpenRecent] = useState(false);
  const [openDownloads, setOpenDownloads] = useState(false);
  const [openTemperature, setOpenTemperature] = useState(false);

  // =========================
  // 📜 RECENT MAINTENANCE LOGS (last 10 min, polls every 5s)
  // =========================
  const [recentLogs, setRecentLogs] = useState([]);
  const [logsError, setLogsError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const fetchLogs = async () => {
      try {
        const res = await fetch(
          "http://localhost:8000/maintenance/logs?minutes=10&limit=200"
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) {
          setRecentLogs(Array.isArray(data) ? data : []);
          setLogsError(null);
        }
      } catch (e) {
        if (!cancelled) setLogsError(e.message);
      }
    };
    fetchLogs();
    const t = setInterval(fetchLogs, 5000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const fmtTime = (iso) => {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString();
    } catch (_e) {
      return iso;
    }
  };

  // Reusable collapsible panel: header is a clickable button with a
  // chevron that rotates 90° on open. Children render only when open
  // so panels with their own data fetching (none here, but future-safe)
  // don't run until the operator looks at them.
  const Panel = ({ title, subtitle, badge, isOpen, onToggle, children }) => (
    <div style={styles.panel}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isOpen}
        style={{
          ...styles.panelHeader,
          background: isOpen
            ? "linear-gradient(145deg, #1e293b, #0b1220)"
            : "linear-gradient(145deg, #111827, #0b1220)",
        }}
      >
        <span
          style={{
            ...styles.panelChevron,
            transform: isOpen ? "rotate(90deg)" : "rotate(0deg)",
          }}
        >
          ▶
        </span>
        <span style={styles.panelTitle}>{title}</span>
        {subtitle && <span style={styles.panelSubtitle}>{subtitle}</span>}
        {badge != null && <span style={styles.panelBadge}>{badge}</span>}
      </button>
      {isOpen && <div style={styles.panelBody}>{children}</div>}
    </div>
  );

  // ==========================================
  // 🔧 MANUAL MAINTENANCE
  // ==========================================
  const handleMaintain = async (machineId) => {
    try {
      const res = await fetch(
        `http://localhost:8000/maintenance/${machineId}`,
        { method: "POST" }
      );

      const data = await res.json();

      if (!data || data.status !== "success") {
        throw new Error("Invalid response");
      }

      console.log("✅ Manual maintenance success:", machineId);

    } catch (err) {
      console.error("❌ Maintenance error:", err);
      alert("Maintenance failed");
    }
  };

  return (
    <div style={styles.container}>

      <header style={styles.header}>
        <div style={styles.headerEyebrow}>SYNAPTIC FABRIC</div>
        <h1 style={styles.title}>Mission Control</h1>
        <div style={styles.headerSubtitle}>
          Autonomous industrial AI · 4-node manufacturing chain · live digital twin
        </div>
      </header>

      <FactoryTwin3D machines={machines} />

      <div style={styles.grid}>
        {Object.values(machines).map((machine) => (
          <MachineCard
            key={machine.machine_id}
            machine={machine}
            onMaintain={handleMaintain}
          />
        ))}
      </div>

      <section style={styles.analytics}>
        <h2 style={styles.sectionTitle}>Factory Intelligence</h2>

        <div style={styles.analyticsGrid}>
          <div style={styles.statCard}>
            <div style={styles.statLabel}>Plant Health Score</div>
            <div style={styles.statValue} className="mono">
              {factoryAnalytics.plant_health_score ?? "—"}
              <span style={styles.statUnit}>%</span>
            </div>
          </div>

          <div style={styles.statCard}>
            <div style={styles.statLabel}>Most Unstable Machine</div>
            <div style={styles.statValue}>
              {factoryAnalytics.most_unstable_machine ?? "—"}
            </div>
          </div>

          <div style={styles.statCard}>
            <div style={styles.statLabel}>Total Machines</div>
            <div style={styles.statValue} className="mono">
              {factoryAnalytics.total_machines ?? "—"}
            </div>
          </div>

          <div style={styles.statCard}>
            <div style={styles.statLabel}>Needs Attention</div>
            <div style={{ ...styles.statValue, fontSize: "18px" }}>
              {(factoryAnalytics.machines_needing_attention || []).join(", ") || "—"}
            </div>
          </div>
        </div>
      </section>

      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>Agent Alerts</h2>

        {agentAlerts.length === 0 ? (
          <p style={styles.emptyHint}>No active alerts.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {agentAlerts.map((a, i) => (
              <div
                key={i}
                style={{
                  ...styles.alertBox,
                  borderLeft: `3px solid ${
                    a.level === "CRITICAL" ? "#ef4444" : "#f59e0b"
                  }`,
                  background:
                    a.level === "CRITICAL"
                      ? "rgba(239, 68, 68, 0.10)"
                      : "rgba(245, 158, 11, 0.10)",
                }}
              >
                <span style={{
                  ...styles.alertLevel,
                  color: a.level === "CRITICAL" ? "#fca5a5" : "#fcd34d",
                }}>
                  {a.level}
                </span>
                <span style={styles.alertMachine} className="mono">{a.machine_id}</span>
                <span style={{ opacity: 0.85 }}>{a.message}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <Panel
        title="Recent Maintenance Activity"
        subtitle="last 10 min · auto-refresh 5s"
        badge={recentLogs.length || null}
        isOpen={openRecent}
        onToggle={() => setOpenRecent((v) => !v)}
      >
        <p style={{ opacity: 0.6, margin: "0 0 12px 0", fontSize: "13px" }}>
          What-if rows are hypothetical and don't reflect real maintenance —
          they're cleared by performing maintenance.
        </p>
        {logsError && (
          <div style={{ color: "#ff5252", fontSize: "12px", marginBottom: 6 }}>
            (logs unreachable: {logsError})
          </div>
        )}
        {recentLogs.length === 0 ? (
          <p style={{ opacity: 0.6 }}>No maintenance events in the last 10 minutes.</p>
        ) : (
          <div style={styles.logTableWrap}>
            <table style={styles.logTable}>
              <thead>
                <tr>
                  <th style={styles.th}>Time</th>
                  <th style={styles.th}>Machine</th>
                  <th style={styles.th}>Action</th>
                  <th style={styles.th}>Status</th>
                  <th style={styles.th}>Source</th>
                  <th style={styles.th}>Health</th>
                  <th style={styles.th}>Risk</th>
                  <th style={styles.th}>Reason</th>
                </tr>
              </thead>
              <tbody>
                {recentLogs.map((row) => (
                  <tr
                    key={row.id}
                    style={row.is_whatif ? styles.trWhatif : styles.tr}
                  >
                    <td style={styles.td}>{fmtTime(row.timestamp)}</td>
                    <td style={styles.td}>{row.machine_id}</td>
                    <td style={styles.td}>
                      {row.action}
                      {row.is_whatif && (
                        <span style={styles.whatifBadge}>WHAT-IF</span>
                      )}
                    </td>
                    <td style={styles.td}>{row.status}</td>
                    <td style={styles.td}>{row.source}</td>
                    <td style={styles.td}>{row.health_status ?? "—"}</td>
                    <td style={styles.td}>
                      {row.risk == null ? "—" : (row.risk * 100).toFixed(0) + "%"}
                    </td>
                    <td style={{ ...styles.td, opacity: 0.8 }}>{row.reason ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* ===================================== */}
      {/* 📥 MAINTENANCE LOG DOWNLOAD (collapsible) */}
      {/* ===================================== */}
      <Panel
        title="Maintenance Log Downloads"
        subtitle="full history export"
        isOpen={openDownloads}
        onToggle={() => setOpenDownloads((v) => !v)}
      >
        <p style={styles.emptyHint}>
          Download every maintenance event (manual, auto-dwell, n8n agent, and
          what-if scenarios) with timestamp, machine, action, status, source,
          health, risk and an <code>is_whatif</code> flag for filtering
          hypothetical rows.
        </p>
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
          <a
            href="http://localhost:8000/maintenance/logs/download?format=csv"
            style={styles.downloadBtn}
          >
            Download CSV
          </a>
          <a
            href="http://localhost:8000/maintenance/logs/download?format=json"
            style={{ ...styles.downloadBtn, background: "rgba(148, 163, 184, 0.10)", color: "#cbd5e1", border: "1px solid rgba(148,163,184,0.25)" }}
          >
            Download JSON
          </a>
        </div>
      </Panel>

      <Panel
        title="Live Temperature"
        subtitle={`window: ${timeRange} min`}
        isOpen={openTemperature}
        onToggle={() => setOpenTemperature((v) => !v)}
      >
        <div style={{ display: "flex", gap: "10px", alignItems: "center", marginBottom: "12px" }}>
          <label style={{ fontSize: "12px", opacity: 0.7 }}>Time window:</label>
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(Number(e.target.value))}
            style={styles.select}
          >
            <option value={1}>Last 1 min</option>
            <option value={5}>Last 5 min</option>
            <option value={10}>Last 10 min</option>
          </select>
        </div>
        <TemperatureChart range={timeRange} />
      </Panel>

      <button
        style={styles.chatButton}
        onClick={() => setShowChatbot(!showChatbot)}
      >
        {showChatbot ? "Close Assistant" : "AI Assistant"}
      </button>

      {showChatbot && (
        <div style={styles.chatPopup}>
          <Chatbot />
        </div>
      )}

      {popupMessage && (
        <div style={styles.popup}>
          {popupMessage}
        </div>
      )}

    </div>
  );
}

export default App;

//
// ==========================================
// 🎨 STYLES
// ==========================================
//

const styles = {
  container: {
    padding: "32px 48px",
    background: "#050810",
    color: "#e2e8f0",
    minHeight: "100vh",
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    maxWidth: "1480px",
    margin: "0 auto",
  },

  header: {
    marginBottom: "28px",
    paddingBottom: "20px",
    borderBottom: "1px solid rgba(148, 163, 184, 0.10)",
  },
  headerEyebrow: {
    fontSize: "11px",
    letterSpacing: "3px",
    fontWeight: 600,
    color: "#60a5fa",
    textTransform: "uppercase",
    marginBottom: "6px",
  },
  title: {
    margin: "0",
    fontSize: "30px",
    fontWeight: 700,
    letterSpacing: "-0.02em",
    color: "#f1f5f9",
  },
  headerSubtitle: {
    marginTop: "6px",
    fontSize: "13px",
    color: "#94a3b8",
    letterSpacing: "0.01em",
  },

  sectionTitle: {
    margin: "0 0 14px 0",
    fontSize: "13px",
    fontWeight: 600,
    letterSpacing: "0.18em",
    textTransform: "uppercase",
    color: "#94a3b8",
  },

  section: {
    marginTop: "32px",
  },

  emptyHint: {
    margin: "0 0 14px 0",
    fontSize: "13px",
    color: "#94a3b8",
    lineHeight: 1.55,
  },

  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
    gap: "18px",
    marginTop: "24px",
  },

  analytics: {
    marginTop: "40px",
  },

  analyticsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: "14px",
  },

  statCard: {
    background: "#0b1220",
    padding: "16px 18px",
    borderRadius: "10px",
    border: "1px solid rgba(148, 163, 184, 0.08)",
    transition: "border 0.2s ease, transform 0.2s ease",
  },
  statLabel: {
    fontSize: "11px",
    fontWeight: 500,
    letterSpacing: "0.15em",
    textTransform: "uppercase",
    color: "#94a3b8",
    marginBottom: "8px",
  },
  statValue: {
    fontSize: "26px",
    fontWeight: 600,
    color: "#f1f5f9",
    letterSpacing: "-0.01em",
  },
  statUnit: {
    fontSize: "16px",
    color: "#94a3b8",
    marginLeft: "3px",
    fontWeight: 500,
  },

  alertBox: {
    padding: "12px 14px",
    borderRadius: "8px",
    fontSize: "13px",
    color: "#e2e8f0",
    display: "flex",
    alignItems: "center",
    gap: "12px",
  },
  alertLevel: {
    fontSize: "10px",
    fontWeight: 700,
    letterSpacing: "0.12em",
    padding: "3px 8px",
    background: "rgba(0, 0, 0, 0.25)",
    borderRadius: "4px",
  },
  alertMachine: {
    fontWeight: 600,
    color: "#f1f5f9",
    fontSize: "13px",
  },

  chatButton: {
    position: "fixed",
    bottom: "20px",
    right: "20px",
    padding: "10px 18px",
    background: "#2563eb",
    color: "white",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
    fontWeight: 600,
    fontSize: "13px",
    letterSpacing: "0.02em",
    boxShadow: "0 6px 18px rgba(37, 99, 235, 0.35)",
    zIndex: 1000,
    transition: "transform 0.15s ease, box-shadow 0.15s ease",
  },

  chatPopup: {
    position: "fixed",
    bottom: "72px",
    right: "20px",
    width: "340px",
    height: "440px",
    background: "#0b1220",
    border: "1px solid rgba(148, 163, 184, 0.15)",
    borderRadius: "12px",
    boxShadow: "0 20px 60px rgba(0, 0, 0, 0.6)",
    overflow: "hidden",
    zIndex: 1000,
  },

  popup: {
    position: "fixed",
    top: "24px",
    left: "50%",
    transform: "translateX(-50%)",
    background: "rgba(15, 23, 42, 0.95)",
    color: "#f1f5f9",
    padding: "12px 22px",
    borderRadius: "8px",
    fontWeight: 500,
    fontSize: "13px",
    letterSpacing: "0.02em",
    border: "1px solid rgba(96, 165, 250, 0.35)",
    boxShadow: "0 8px 30px rgba(0, 0, 0, 0.5)",
    backdropFilter: "blur(12px)",
    zIndex: 3000,
  },

  downloadBtn: {
    display: "inline-block",
    padding: "9px 16px",
    background: "#2563eb",
    color: "white",
    textDecoration: "none",
    borderRadius: "6px",
    fontWeight: 600,
    fontSize: "13px",
    letterSpacing: "0.02em",
    border: "1px solid rgba(96, 165, 250, 0.25)",
    transition: "background 0.15s ease",
  },

  logTableWrap: {
    maxHeight: "220px",
    overflowY: "auto",
    overflowX: "auto",
    border: "1px solid rgba(148, 163, 184, 0.08)",
    borderRadius: "8px",
    background: "#0b1220",
    scrollbarWidth: "thin",
    scrollbarColor: "rgba(148,163,184,0.4) transparent",
  },
  logTable: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "12.5px",
    fontFamily: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
  },
  th: {
    position: "sticky",
    top: 0,
    zIndex: 1,
    textAlign: "left",
    padding: "10px 12px",
    background: "#0f172a",
    borderBottom: "1px solid rgba(148, 163, 184, 0.12)",
    fontWeight: 600,
    fontSize: "10px",
    letterSpacing: "0.16em",
    textTransform: "uppercase",
    color: "#64748b",
    fontFamily: "'Inter', sans-serif",
  },
  td: {
    padding: "9px 12px",
    borderBottom: "1px solid rgba(148, 163, 184, 0.04)",
    color: "#cbd5e1",
  },
  tr: {},
  trWhatif: {
    background: "rgba(245, 158, 11, 0.05)",
  },
  whatifBadge: {
    display: "inline-block",
    marginLeft: "8px",
    padding: "1px 6px",
    fontSize: "9px",
    fontWeight: 700,
    letterSpacing: "0.1em",
    color: "#fcd34d",
    background: "rgba(245, 158, 11, 0.15)",
    border: "1px solid rgba(245, 158, 11, 0.35)",
    borderRadius: "3px",
    fontFamily: "'Inter', sans-serif",
  },

  // ----- Collapsible panels -----
  panel: {
    marginTop: "12px",
    borderRadius: "10px",
    overflow: "hidden",
    border: "1px solid rgba(148, 163, 184, 0.08)",
    background: "#0b1220",
  },
  panelHeader: {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: "12px",
    padding: "14px 18px",
    border: "none",
    color: "#e2e8f0",
    cursor: "pointer",
    textAlign: "left",
    transition: "background 0.15s ease",
    fontFamily: "inherit",
  },
  panelChevron: {
    display: "inline-block",
    fontSize: "10px",
    color: "#64748b",
    transition: "transform 0.2s ease",
    width: "14px",
    flex: "0 0 14px",
  },
  panelTitle: {
    fontSize: "13px",
    fontWeight: 600,
    letterSpacing: "0.05em",
    color: "#f1f5f9",
  },
  panelSubtitle: {
    fontSize: "11px",
    color: "#64748b",
    fontWeight: 400,
    letterSpacing: "0.02em",
    marginLeft: "4px",
  },
  panelBadge: {
    marginLeft: "auto",
    background: "rgba(37, 99, 235, 0.15)",
    color: "#93c5fd",
    border: "1px solid rgba(147, 197, 253, 0.20)",
    borderRadius: "4px",
    padding: "2px 8px",
    fontSize: "10px",
    fontWeight: 600,
    letterSpacing: "0.08em",
    fontFamily: "'JetBrains Mono', monospace",
  },
  panelBody: {
    padding: "16px 18px 18px 18px",
    borderTop: "1px solid rgba(148, 163, 184, 0.06)",
    background: "#070d1a",
  },

  select: {
    padding: "7px 12px",
    background: "#070d1a",
    color: "#e2e8f0",
    border: "1px solid rgba(148, 163, 184, 0.18)",
    borderRadius: "6px",
    fontSize: "12px",
    fontFamily: "inherit",
  },
};