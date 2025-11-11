// ui/dashboard/src/components/EventTrends.jsx
// -----------------------------------------------------------------------------
// EventTrends.jsx
// Visualizes incoming honeypot events as a line chart over time.
// What it does:
//   • Fetches /api/events?limit=100 periodically
//   • Groups events by *minute* (UTC minute buckets) to smooth out spikes
//   • Renders a responsive Recharts LineChart
//   • Respects dark/light theme via `dark` prop
//   • Shows loading + empty states cleanly
//   • Fades in data on refresh
//
// Notes on layout / Recharts quirks:
//   • Recharts needs a real width/height from parent containers. If a parent
//     is a flex item with overflow constraints, width can measure as -1.
//     To prevent that, we:
//       - wrap the chart in a container with explicit height (e.g. 260px)
//       - set minWidth: 0 so flexbox can shrink and compute width correctly
//   • The parent wrapper in App.jsx was updated to include `min-w-0`.
// -----------------------------------------------------------------------------

import { useEffect, useState, useMemo } from "react";
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
  // Chart-ready rows: [{ time: "HH:MM", count: number }, ...]
  const [data, setData] = useState([]);
  // Loading flag so we can show spinner until first paint
  const [loading, setLoading] = useState(true);
  // Optional error message (network or parse issues)
  const [error, setError] = useState(null);

  // --- Fetch raw events from API ---------------------------------------------
  // We keep this as a separate function so we can call it:
  //   • on mount
  //   • on an interval (every 10s)
  async function fetchData() {
    try {
      setLoading(true);
      setError(null);

      // If your backend requires an API key for /api/events,
      // include it here (it’s harmless if the backend ignores it).
      const res = await fetch("/api/events?limit=100", {
        headers: { "x-api-key": "dev-123" },
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const json = await res.json();

      // Backend may return either an array or { items: [...] }.
      // This normalizes to a consistent array.
      const events = Array.isArray(json) ? json : json.items ?? json.events ?? [];

      // --- Bucket by minute (UTC) --------------------------------------------
      // Map<stringMinute, count>
      // Example key: "2025-11-07T09:47"
      const buckets = new Map();

      for (const ev of events) {
        // Accept a few common timestamp field names; skip if none
        const ts = ev?.ts || ev?.time || ev?.timestamp;
        if (!ts) continue;

        // Tolerate both ISO strings and epoch numbers
        const d =
          typeof ts === "number"
            ? new Date(ts)
            : new Date(ts); // new Date() also accepts ISO

        // Skip unparseable dates
        if (isNaN(d.getTime())) continue;

        // Round down to the minute in UTC by formatting a "YYYY-MM-DD HH:MM" key
        const key = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(
          2,
          "0"
        )}-${String(d.getUTCDate()).padStart(2, "0")} ${String(
          d.getUTCHours()
        ).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;

        buckets.set(key, (buckets.get(key) || 0) + 1);
      }

      // --- Convert into chart rows ------------------------------------------
      // We sort by key (ascending chronological order) and then format labels
      const rows = Array.from(buckets.entries())
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([k, count]) => {
          // k is "YYYY-MM-DD HH:MM" (UTC). Convert to a compact local HH:MM label.
          // Using local time for readability; if you prefer UTC, keep as k.slice(11).
          const [datePart, hm] = k.split(" ");
          const label = new Date(`${datePart}T${hm}:00Z`).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          });
          return { time: label, count };
        });

      setData(rows);
    } catch (e) {
      console.error("EventTrends fetch error:", e);
      setError(e?.message || "Fetch failed");
      // On error we keep previous data so the chart doesn’t disappear abruptly
    } finally {
      setLoading(false);
    }
  }

  // --- Initial + periodic refresh -------------------------------------------
  useEffect(() => {
    // First load immediately
    fetchData();

    // Then refresh every 10 seconds
    const id = setInterval(fetchData, 10_000);
    return () => clearInterval(id);
  }, []);

  // --- Derived chart theming (memoized) --------------------------------------
  const styles = useMemo(
    () => ({
      gridColor: dark ? "rgba(255,255,255,0.08)" : "#e5e5e5",
      axisColor: dark ? "#cbd5e1" : "#334155",
      strokeColor: dark ? "#4ade80" : "#047857",
      cardBg: dark ? "rgba(255,255,255,0.02)" : "#fafafa",
    }),
    [dark]
  );

  // --- Empty state (only after first load) -----------------------------------
  if (!loading && data.length === 0 && !error) {
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

  // --- Loading (first paint) -------------------------------------------------
  // After first data appears, we keep showing the chart and just fade it
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
              to   { transform: rotate(360deg); }
            }
          `}
        </style>
      </div>
    );
  }

  // --- Chart render ----------------------------------------------------------
  return (
    <div
      // Explicit chart container that Recharts can measure:
      //  • width: 100% so it fills the card
      //  • height: 260 so ResponsiveContainer has real pixels to measure
      //  • minWidth: 0 so flexbox can shrink it (prevents width -1)
      style={{
        width: "100%",
        height: 260,
        minWidth: 0,
        opacity: loading ? 0.5 : 1,
        transition: "opacity 0.8s ease-in-out", // smooth fade between updates
        backgroundColor: styles.cardBg,
        borderRadius: "12px",
        padding: "1rem",
        animation: "fadeIn 0.8s ease-in-out",
      }}
    >
      {/* Title */}
      <h3
        style={{
          marginBottom: "0.6rem",
          fontWeight: 500,
          opacity: 0.9,
        }}
      >
        Event Trends (last 100 events)
      </h3>

      {/* Optional small error banner (keeps chart visible if we have older data) */}
      {error && (
        <div
          style={{
            marginBottom: 8,
            fontSize: 12,
            color: "#ef4444",
            opacity: 0.9,
          }}
        >
          Error: {String(error)}
        </div>
      )}

      {/* Recharts wrapper; now safe because parent has a real height */}
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={styles.gridColor} />
          <XAxis
            dataKey="time"
            stroke={styles.axisColor}
            tick={{ fontSize: 12 }}
            minTickGap={28}
            tickLine={false}
            axisLine={{ stroke: styles.axisColor }}
          />
          <YAxis
            allowDecimals={false}
            stroke={styles.axisColor}
            tick={{ fontSize: 12 }}
            width={32}
            tickLine={false}
            axisLine={{ stroke: styles.axisColor }}
          />
          <Tooltip
            labelStyle={{ fontSize: 12 }}
            contentStyle={{ borderRadius: 8 }}
          />
          <Line
            type="monotone"
            dataKey="count"
            stroke={styles.strokeColor}
            strokeWidth={2}
            dot={false}
            isAnimationActive={true} // animate line on update
          />
        </LineChart>
      </ResponsiveContainer>

      {/* Subtle mount animation */}
      <style>
        {`
          @keyframes fadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to   { opacity: 1; transform: translateY(0); }
          }
        `}
      </style>
    </div>
  );
}
