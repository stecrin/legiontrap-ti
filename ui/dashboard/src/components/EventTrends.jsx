// ui/dashboard/src/components/EventTrends.jsx
// -----------------------------------------------------------------------------
// EventTrends.jsx
// Visualizes incoming honeypot events as a line chart over time.
// - Fetches /api/events?limit=100 every 10s
// - Groups by minute
// - Uses Recharts LineChart with smooth transitions
// - Respects dark/light theme via `dark` prop
// - Displays a line chart of recent event counts
// - Uses Recharts for responsive visualisation
// - Auto-fades in on each data refresh
// - Handles empty state ("No data yet")
// -----------------------------------------------------------------------------

import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export default function EventTrends({ dark }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  // --- Fetch data ------------------------------------------------------------
  async function fetchData() {
    try {
      setLoading(true);
      const res = await fetch("/api/events?limit=100", {
        headers: { "x-api-key": "dev-123" },
      });
      const json = await res.json();

      // Normalise to array (backend may return {items: []} or [])
      const events = Array.isArray(json)
        ? json
        : json.items ?? json.events ?? [];

      // Group by minute (rounded timestamp)
      const grouped = {};
      for (const e of events) {
        const ts = new Date(e.ts);
        if (isNaN(ts)) continue; // skip invalid dates
        const minute = ts.toISOString().slice(0, 16); // e.g. 2025-11-07T09:47
        grouped[minute] = (grouped[minute] || 0) + 1;
      }

      // Convert to chart-friendly format
      const chartData = Object.entries(grouped)
        .map(([k, v]) => ({
          time: new Date(k).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
          count: v,
        }))
        .sort(
          (a, b) =>
            new Date("1970/01/01 " + a.time) -
            new Date("1970/01/01 " + b.time)
        );

      setData(chartData);
    } catch (err) {
      console.error("EventTrends fetch error:", err);
    } finally {
      setLoading(false);
    }
  }

  // --- Initial + periodic refresh -------------------------------------------
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10_000);
    return () => clearInterval(interval);
  }, []);

  // --- Empty state fallback --------------------------------------------------
  if (!loading && data.length === 0) {
    return (
      <div
        style={{
          textAlign: "center",
          padding: "2rem",
          opacity: 0.7,
          fontStyle: "italic",
        }}
      >
        No data yet — waiting for events…
      </div>
    );
  }

  // --- Loading spinner ------------------------------------------------------
  if (loading && data.length === 0) {
    return (
      <div
        style={{
          textAlign: "center",
          padding: "2rem",
          opacity: 0.8,
        }}
      >
        <div
          style={{
            display: "inline-block",
            width: 24,
            height: 24,
            border: "3px solid transparent",
            borderTop: "3px solid #22c55e",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }}
        />
        <p style={{ marginTop: 8 }}>Loading trends…</p>
        <style>
          {`
            @keyframes spin {
              from { transform: rotate(0deg); }
              to { transform: rotate(360deg); }
            }
          `}
        </style>
      </div>
    );
  }

  // --- Chart render ----------------------------------------------------------
  return (
    <div
      style={{
        width: "100%",
        height: 260,
        opacity: loading ? 0.5 : 1,
        transition: "opacity 0.8s ease-in-out", // ✅ smooth fade-in
        backgroundColor: dark ? "rgba(255,255,255,0.02)" : "#fafafa",
        borderRadius: "12px",
        padding: "1rem",
        animation: "fadeIn 0.8s ease-in-out",
      }}
    >
      <h3
        style={{
          marginBottom: "0.6rem",
          fontWeight: 500,
          opacity: 0.9,
        }}
      >
        Event Trends (last 100 events)
      </h3>

      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke={dark ? "rgba(255,255,255,0.08)" : "#e5e5e5"}
          />
          <XAxis
            dataKey="time"
            stroke={dark ? "#ccc" : "#333"}
            tick={{ fontSize: 12 }}
          />
          <YAxis
            allowDecimals={false}
            stroke={dark ? "#ccc" : "#333"}
            tick={{ fontSize: 12 }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: dark ? "#1f1f1f" : "#fff",
              borderRadius: 8,
              border: "1px solid rgba(255,255,255,0.1)",
              fontSize: 12,
            }}
          />
          <Line
            type="monotone"
            dataKey="count"
            stroke={dark ? "#4ade80" : "#047857"}
            strokeWidth={2}
            dot={false}
            isAnimationActive={true} // ✅ animate line
          />
        </LineChart>
      </ResponsiveContainer>

      <style>
        {`
          @keyframes fadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}
      </style>
    </div>
  );
}
