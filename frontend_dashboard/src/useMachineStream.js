import { useEffect, useState, useRef } from "react";

export default function useMachineStream() {

  // ==========================================
  // 📊 STATE
  // ==========================================
  const [machines, setMachines] = useState({});
  const [factoryAnalytics, setFactoryAnalytics] = useState({});
  const [agentAlerts, setAgentAlerts] = useState([]);
  const [agentActions, setAgentActions] = useState([]);

  // 🚀 POPUP SYSTEM
  const [popupMessage, setPopupMessage] = useState(null);

  const popupQueueRef = useRef([]);
  const isShowingRef = useRef(false);

  // ✅ TRACK SHOWN ACTIONS (NO DUPLICATES)
  const shownActionsRef = useRef(new Set());

  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  // ==========================================
  // 🎯 POPUP QUEUE ENGINE
  // ==========================================
  const processPopupQueue = () => {

    if (isShowingRef.current) return;
    if (popupQueueRef.current.length === 0) return;

    const next = popupQueueRef.current.shift();

    isShowingRef.current = true;

    setPopupMessage(next);

    setTimeout(() => {
      setPopupMessage(null);
      isShowingRef.current = false;

      // 🔁 NEXT POPUP
      processPopupQueue();

    }, 3000);
  };

  // ==========================================
  // 🔌 WEBSOCKET CONNECTION
  // ==========================================
  useEffect(() => {

    const connectWebSocket = () => {

      console.log("🔌 Connecting WS...");

      const ws = new WebSocket("ws://127.0.0.1:8000/ws/machines");
      wsRef.current = ws;

      // =========================
      // ✅ CONNECTED
      // =========================
      ws.onopen = () => {
        console.log("✅ WebSocket connected");
      };

      // =========================
      // 📡 MESSAGE RECEIVED
      // =========================
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);

          const machineArray = payload?.machines || [];
          const analytics = payload?.factory_analytics || {};
          const alerts = payload?.agent_alerts || [];
          const actions = payload?.agent_actions || [];

          const mapped = {};

          // ======================================
          // 🏭 MACHINE DATA MAPPING
          // ======================================
          machineArray.forEach((m) => {

            const id = m.machine_id;

            mapped[id] = {
              machine_id: id,

              temperature: m.temperature ?? 0,
              torque: m.torque ?? 0,
              tool_wear: m.tool_wear ?? 0,
              vibration_index: m.vibration_index ?? 0,

              health_status: m.health_status ?? "Unknown",
              prediction: m.prediction ?? m.anomaly_score ?? 0,
              anomaly_score: m.anomaly_score ?? 0,

              alerts: (m.alerts || []).map((a) => ({
                level: (a.level || "info").toUpperCase(),
                message: a.message || "No message"
              })),

              diagnosis: (m.root_cause || []).map((c) => ({
                issue: c.issue || "Unknown",
                confidence: c.confidence ?? 0,
                reason: c.reason || ""
              })),

              rul_cycles: m.rul_cycles ?? null,
              rul_time: m.rul_time ?? null,

              ai_explanation: m.ai_explanation ?? "",
              shap: m.shap ?? {},

              future_prediction: m.future_prediction ?? null
            };
          });

          // ======================================
          // ✅ STATE UPDATE
          // ======================================
          setMachines(mapped);
          setFactoryAnalytics(analytics);
          setAgentAlerts(alerts);
          setAgentActions(actions);

          // ======================================
          // 🚀 POPUP LOGIC
          //   Fires for AUTO_MAINTENANCE (dwell rule),
          //   MANUAL_MAINTENANCE (dashboard button), and
          //   WHAT_IF_REVERT (any path that drains a what-if scenario).
          // ======================================
          actions.forEach((a) => {

            const act = a.action;
            const supported =
              act === "AUTO_MAINTENANCE" ||
              act === "MANUAL_MAINTENANCE" ||
              act === "WHAT_IF_REVERT";
            if (!supported) return;

            // 🔥 SAFE UNIQUE KEY
            const uniqueKey = `${a.machine_id}-${a.timestamp}-${a.status}-${act}`;
            if (shownActionsRef.current.has(uniqueKey)) return;
            shownActionsRef.current.add(uniqueKey);

            let msg = "";

            if (act === "WHAT_IF_REVERT") {
              if (a.status === "STARTING") {
                msg = `↩️ Reverting what-if scenario on ${a.machine_id}`;
              } else if (a.status === "SUCCESS" || a.status === "APPLIED") {
                msg = `✅ ${a.machine_id} restored to pre-spike state`;
              }
            } else {
              // AUTO_MAINTENANCE or MANUAL_MAINTENANCE
              if (a.status === "STARTING") {
                msg = `⚙️ Performing maintenance on ${a.machine_id}`;
              } else if (a.status === "SUCCESS") {
                msg = `✅ Maintenance completed for ${a.machine_id}`;
              }
            }

            if (msg) {
              popupQueueRef.current.push(msg);
            }
          });

          processPopupQueue();

        } catch (err) {
          console.error("❌ WS PARSE ERROR:", err);
        }
      };

      // =========================
      // ❌ ERROR
      // =========================
      ws.onerror = (err) => {
        console.error("❌ WebSocket error:", err);
      };

      // =========================
      // 🔁 RECONNECT
      // =========================
      ws.onclose = () => {
        console.warn("⚠️ WS closed. Reconnecting...");

        reconnectRef.current = setTimeout(() => {
          connectWebSocket();
        }, 2000);
      };
    };

    connectWebSocket();

    // =========================
    // CLEANUP
    // =========================
    return () => {
      console.log("🔌 Cleaning WS...");

      if (wsRef.current) wsRef.current.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };

  }, []);

  // ==========================================
  // 📦 RETURN STATE
  // ==========================================
  return {
    machines,
    factoryAnalytics,
    agentAlerts,
    agentActions,
    popupMessage
  };
}