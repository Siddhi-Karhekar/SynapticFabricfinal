import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine
} from "recharts";
import { useEffect, useState } from "react";

export default function TemperatureChart({ range }) {

  const [history, setHistory] = useState([]);

  useEffect(() => {

    const fetchHistory = async () => {

      try {
        const apiHost = window.location.hostname;
        const apiProtocol = window.location.protocol;
        const apiUrl = `${apiProtocol}//${apiHost}:8000/history?minutes=${range}`;

        const res = await fetch(apiUrl);

        const data = await res.json();

        // ✅ SAFETY CHECK (CRITICAL FIX)
        if (Array.isArray(data)) {
          setHistory(data);
        } else {
          console.error("❌ Invalid API format:", data);
          setHistory([]);
        }

      } catch (err) {
        console.error("❌ History fetch error:", err);
        setHistory([]);
      }
    };

    fetchHistory();

    const interval = setInterval(fetchHistory, 5000);

    return () => clearInterval(interval);

  }, [range]);

  return (
    <LineChart width={750} height={320} data={history || []}>

      {/* GRID */}
      <CartesianGrid stroke="#222" />

      {/* X AXIS */}
      <XAxis
        dataKey="time"
        tick={{ fill: "#aaa", fontSize: 11 }}
      />

      {/* Y AXIS */}
      <YAxis
        domain={[290, 310]}
        tick={{ fill: "#aaa", fontSize: 12 }}
      />

      {/* TOOLTIP */}
      <Tooltip
        contentStyle={{
          backgroundColor: "#111",
          border: "1px solid #333",
          color: "#fff",
        }}
        formatter={(value) =>
          value !== null && value !== undefined
            ? `${value.toFixed(2)} °C`
            : "--"
        }
      />

      {/* LEGEND */}
      <Legend />

      {/* THRESHOLDS */}
      <ReferenceLine y={300} stroke="#ffaa00" strokeDasharray="5 5" />
      <ReferenceLine y={305} stroke="#ff4444" strokeDasharray="5 5" />

      {/* MACHINE LINES */}
      <Line type="monotone" dataKey="M_1" name="Induction Motor"     stroke="#00ff88" strokeWidth={3} dot={false}/>
      <Line type="monotone" dataKey="M_2" name="Industrial Gearbox"  stroke="#ffaa00" strokeWidth={3} dot={false}/>
      <Line type="monotone" dataKey="M_3" name="CNC Milling Tool"    stroke="#ff4444" strokeWidth={3} dot={false}/>
      <Line type="monotone" dataKey="M_4" name="Robotic Sorting Arm" stroke="#3aa0ff" strokeWidth={3} dot={false}/>

    </LineChart>
  );
}