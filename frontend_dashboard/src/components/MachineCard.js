import React, { useState, useEffect } from "react";
import "./MachineCard.css";
import { MACHINE_INFO } from "../utils/machineInfo";

export default function MachineCard({ machine, onMaintain }) {
  const [maintaining, setMaintaining] = useState(false);
  const [showSpike, setShowSpike] = useState(false);
  const [spikeBusy, setSpikeBusy] = useState(false);
  const [spikeFields, setSpikeFields] = useState({
    temperature: "",
    torque: "",
    tool_wear: "",
    vibration_index: "",
  });

  useEffect(() => {
    if (!showSpike) {
      setSpikeFields({
        temperature: (machine.temperature ?? 0).toFixed(2),
        torque: (machine.torque ?? 0).toFixed(2),
        tool_wear: (machine.tool_wear ?? 0).toFixed(3),
        vibration_index: (machine.vibration_index ?? 0).toFixed(3),
      });
    }
  }, [machine, showSpike]);

  const submitSpike = async () => {
    setSpikeBusy(true);
    try {
      const body = {};
      for (const k of ["temperature", "torque", "tool_wear", "vibration_index"]) {
        const v = parseFloat(spikeFields[k]);
        if (!Number.isNaN(v)) body[k] = v;
      }
      const res = await fetch(`http://localhost:8000/spike/${machine.machine_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.status !== "success") throw new Error(data.message || "spike failed");
      setShowSpike(false);
    } catch (e) {
      console.error("Spike error:", e);
      alert("Spike injection failed: " + e.message);
    }
    setSpikeBusy(false);
  };

  const info = MACHINE_INFO[machine.machine_id] || {};
  const name = info.name || machine.machine_id;
  const process = info.process || "Unknown Process";

  const handleMaintainClick = async () => {
    setMaintaining(true);
    try {
      await onMaintain(machine.machine_id);
    } catch (e) {
      console.error("Maintenance error:", e);
    }
    setMaintaining(false);
  };

  const temp = machine.temperature ?? 0;
  const torque = machine.torque ?? 0;
  const wear = machine.tool_wear ?? 0;
  const vib = machine.vibration_index ?? 0;
  const prediction = machine.prediction ?? 0;
  const rulCycles = machine.rul_cycles ?? null;
  const rulTime = machine.rul_time ?? null;

  const STATUS_TONE = {
    Healthy: { fg: "#34d399", bg: "rgba(52, 211, 153, 0.10)", border: "rgba(52, 211, 153, 0.30)" },
    Warning: { fg: "#fbbf24", bg: "rgba(251, 191, 36, 0.10)", border: "rgba(251, 191, 36, 0.30)" },
    Critical: { fg: "#f87171", bg: "rgba(248, 113, 113, 0.10)", border: "rgba(248, 113, 113, 0.35)" },
  };
  const tone = STATUS_TONE[machine.health_status] || STATUS_TONE.Critical;

  const riskColor =
    prediction > 0.7 ? "#f87171" : prediction > 0.4 ? "#fbbf24" : "#34d399";

  const cardClass =
    machine.health_status === "Critical"
      ? "machine-card critical-glow"
      : machine.health_status === "Warning"
      ? "machine-card warning-glow"
      : "machine-card";

  return (
    <div className={cardClass}>
      {/* HEADER: machine code + status pill */}
      <div className="mc-head">
        <div>
          <div className="mc-code mono">{machine.machine_id}</div>
          <div className="mc-name">{name}</div>
          <div className="mc-process">{process}</div>
        </div>
        <div
          className="mc-status"
          style={{
            color: tone.fg,
            background: tone.bg,
            borderColor: tone.border,
          }}
        >
          <span className="mc-status-dot" style={{ background: tone.fg }} />
          {machine.health_status}
        </div>
      </div>

      {/* METRIC GRID */}
      <div className="mc-metrics">
        <Metric label="TEMP"      value={temp.toFixed(2)}  unit="K" />
        <Metric label="TORQUE"    value={torque.toFixed(2)} unit="Nm" />
        <Metric label="WEAR"      value={(wear * 100).toFixed(1)} unit="%" />
        <Metric label="VIBRATION" value={vib.toFixed(3)}   unit="" />
      </div>

      {/* RISK */}
      <div className="mc-risk">
        <div className="mc-risk-row">
          <span className="mc-risk-label">FAILURE RISK</span>
          <span className="mc-risk-value mono" style={{ color: riskColor }}>
            {(prediction * 100).toFixed(0)}%
          </span>
        </div>
        <div className="mc-risk-bar">
          <div
            className="mc-risk-fill"
            style={{
              width: `${prediction * 100}%`,
              background: riskColor,
            }}
          />
        </div>
      </div>

      {/* RUL */}
      <div className="mc-rul">
        <div className="mc-rul-cell">
          <div className="mc-rul-label">RUL CYCLES</div>
          <div className="mc-rul-value mono">
            {rulCycles !== null ? rulCycles : "—"}
          </div>
        </div>
        <div className="mc-rul-cell">
          <div className="mc-rul-label">EST. TIME</div>
          <div className="mc-rul-value mono">{rulTime ?? "—"}</div>
        </div>
      </div>

      {/* ACTIONS */}
      <button
        onClick={handleMaintainClick}
        disabled={maintaining}
        className="mc-btn mc-btn-primary"
      >
        {maintaining ? "Maintaining..." : "Perform Maintenance"}
      </button>

      <button
        onClick={() => setShowSpike((v) => !v)}
        className="mc-btn mc-btn-spike"
      >
        {showSpike ? "Cancel" : "Inject Spike"}
      </button>

      {showSpike && (
        <div className="mc-spike-panel">
          <div className="mc-spike-hint">
            Hypothetical override. Maintenance reverts the entire scenario.
          </div>
          {[
            ["temperature", "TEMP", "K"],
            ["torque", "TORQUE", "Nm"],
            ["tool_wear", "WEAR", "0–1"],
            ["vibration_index", "VIBRATION", "0–1"],
          ].map(([k, label, unit]) => (
            <label key={k} className="mc-spike-row">
              <span className="mc-spike-label">{label}</span>
              <input
                type="number"
                step="0.01"
                value={spikeFields[k]}
                onChange={(e) =>
                  setSpikeFields((p) => ({ ...p, [k]: e.target.value }))
                }
                className="mc-spike-input mono"
              />
              <span className="mc-spike-unit">{unit}</span>
            </label>
          ))}
          <button
            onClick={submitSpike}
            disabled={spikeBusy}
            className="mc-btn mc-btn-apply"
          >
            {spikeBusy ? "Injecting..." : "Apply Spike"}
          </button>
        </div>
      )}

      {/* INSPECTION */}
      <div className="mc-inspection">
        <div className="mc-inspection-title">INSPECTION</div>
        {(!machine.diagnosis || machine.diagnosis.length === 0) ? (
          <div className="mc-inspection-ok">No issues detected.</div>
        ) : (
          machine.diagnosis.map((c, i) => (
            <div key={i} className="mc-issue">
              <div className="mc-issue-head">
                <span className="mc-issue-title">{c.issue}</span>
                <span className="mc-issue-conf mono">
                  {((c.confidence ?? 0) * 100).toFixed(0)}%
                </span>
              </div>
              {c.reason && <div className="mc-issue-reason">{c.reason}</div>}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function Metric({ label, value, unit }) {
  return (
    <div className="mc-metric">
      <div className="mc-metric-label">{label}</div>
      <div className="mc-metric-value">
        <span className="mono">{value}</span>
        {unit && <span className="mc-metric-unit">{unit}</span>}
      </div>
    </div>
  );
}
