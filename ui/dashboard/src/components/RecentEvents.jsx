// ui/dashboard/src/components/RecentEvents.jsx
// -----------------------------------------------------------------------------
// Recent Events table
// - Polls /api/events every 10s
// - Shows "Updated X seconds ago" that ticks every second (no manual refresh needed)
// - Live/Offline dot (green = last fetch OK, red = last fetch failed)
// - Loading spinner during active fetch
// - Fade-in animation for table rows after each successful fetch
// - Animated counter text for "Updated Xs ago"
// - Monospace + dark console styling for readability
// -----------------------------------------------------------------------------

import { useEffect, useRef, useState } from "react";
import { timeAgo, safe } from "../utils/format";

const REFRESH_MS = 10_000; // how often we hit the backend

export default function RecentEvents({ dark }) {
  // --- state -----------------------------------------------------------------
  const [rows, setRows] = useState([]);           // events to display
  const [loading, setLoading] = useState(true);   // table loading state (first render)
  const [lastUpdated, setLastUpdated] = useState(null); // last successful fetch time
  const [online, setOnline] = useState(true);     // backend reachability
  const [tick, setTick] = useState(0);            // forces "Updated Xs ago" re-render
  const timerRef = useRef(null);                  // polling interval handle

  // --- helper to build stable unique keys ------------------------------------
  function getRowKey(e, idx) {
    const ts = e.ts || e.time || e.timestamp || "";
    const id = e.id || e._id || ts || "";
    const src = e.src_ip || e.ip || "";
    return (id ? String(id) : `row-${idx}`) + "-" + (src ? String(src) : idx);
  }

  // --- data fetcher ----------------------------------------------------------
  async function fetchEvents(signal) {
    try {
      setLoading(true); // ✅ start spinner
      const res = await fetch("/api/events?limit=10", {
        signal,
        headers: { "x-api-key": "dev-123" },
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      const items = Array.isArray(data)
        ? data
        : (data.items ?? data.events ?? []);

      // newest → oldest
      items.sort((a, b) => new Date(b.ts) - new Date(a.ts));

      // small delay to allow fade animation
      setRows([]);
      setTimeout(() => {
        setRows(items);
        setLastUpdated(new Date());
        setOnline(true);
      }, 150); // ✅ short fade reset
    } catch (e) {
      if (e.name !== "AbortError") {
        console.error("fetchEvents error:", e);
        setOnline(false);
      }
    } finally {
      setLoading(false);
    }
  }

  // --- start polling every REFRESH_MS ---------------------------------------
  useEffect(() => {
    const ctrl = new AbortController();
    fetchEvents(ctrl.signal); // initial

    timerRef.current = setInterval(() => {
      const c = new AbortController();
      fetchEvents(c.signal);
    }, REFRESH_MS);

    return () => {
      ctrl.abort();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  // --- 1s ticker so "Updated Xs ago" animates live ---------------------------
  useEffect(() => {
    const t = setInterval(() => setTick((n) => (n + 1) % 1_000_000), 1000);
    return () => clearInterval(t);
  }, []);

  // --- status dot component --------------------------------------------------
  function StatusDot({ live, style }) {
    const color = live ? "#22c55e" : "#ef4444";
    const title = live ? "Live (backend OK)" : "Offline (last fetch failed)";
    return (
      <>
        <span
          title={title}
          aria-label={title}
          style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            background: color,
            display: "inline-block",
            marginRight: 6,
            verticalAlign: "middle",
            position: "relative",
            top: "-1px",
            boxShadow: `0 0 10px ${color}66`,
            animation: live
              ? "pulseDot 1.6s ease-in-out infinite"
              : "fadeOffline 2s ease-in-out infinite",
            transition: "all 0.4s ease",
            ...style,
          }}
        />
        <style>
          {`
            @keyframes pulseDot {
              0%,100%{transform:scale(1);opacity:1;box-shadow:0 0 10px ${color}66;}
              50%{transform:scale(1.4);opacity:0.6;box-shadow:0 0 16px ${color}99;}
            }
            @keyframes fadeOffline {
              0%,100%{opacity:.6;transform:scale(1);}
              50%{opacity:.25;transform:scale(.9);}
            }
          `}
        </style>
      </>
    );
  }

  // --- render ---------------------------------------------------------------
  return (
    <div className="mt-6 font-mono" // ✅ monospace console look
         style={{ color: dark ? "#E5E7EB" : "#111827" }}>
      {/* Header section: title + controls */}
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-semibold tracking-tight">Recent Events</h2>

        <div className="flex items-center flex-nowrap whitespace-nowrap">
          {/* Refresh button */}
          <button
            onClick={() => fetchEvents(new AbortController().signal)}
            className="px-3 py-1 rounded-md border hover:opacity-90 transition"
            style={{
              lineHeight: "1.2",
              flexShrink: 0,
              marginRight: "1.25rem",
            }}
          >
            Refresh
          </button>

          {/* 🌀 Spinner */}
          {loading && (
            <div
              style={{
                width: 16,
                height: 16,
                border: "2px solid transparent",
                borderTop: `2px solid ${dark ? "#4ade80" : "#22c55e"}`,
                borderRadius: "50%",
                animation: "spin 0.8s linear infinite",
                marginRight: 12,
              }}
              title="Loading..."
            />
          )}

          {/* 🟢/🔴 Status + Updated counter */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              flexShrink: 0,
              gap: "0.6rem",
              color: online ? (dark ? "#A7F3D0" : "#047857") : "#EF4444",
              transform: "translateY(1px)",
            }}
          >
            <StatusDot live={online} />
            <span
              className="whitespace-nowrap transition-all duration-300 ease-in-out"
              style={{
                opacity: loading ? 0.6 : 1,
                transition: "opacity 0.4s ease, transform 0.3s ease",
              }}
            >
              {lastUpdated
                ? `Updated ${timeAgo(lastUpdated)}`
                : loading
                ? "Loading…"
                : "—"}
            </span>
          </div>

          {/* Spinner animation */}
          <style>{`
            @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
          `}</style>
        </div>
      </div>

      {/* --- Table ----------------------------------------------------------- */}
      <div
        className="overflow-hidden rounded-xl border"
        style={{
          background: dark ? "#111827" : "#f9fafb",
          borderColor: dark ? "#374151" : "#d1d5db",
        }}
      >
        <table className="w-full text-sm">
          <thead className="bg-black/5 dark:bg-white/5">
            <tr>
              <Th>Time</Th>
              <Th>Src IP</Th>
              <Th>Dst IP</Th>
              <Th>Type</Th>
              <Th>Country</Th>
            </tr>
          </thead>

          <tbody className="divide-y">
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={5} className="py-4 text-center opacity-70">
                  No events yet.
                </td>
              </tr>
            )}

            {rows.map((e, idx) => {
              const ts = e.ts || e.time || e.timestamp || null;
              const baseColor = dark
                ? idx % 2 === 0
                  ? "rgba(255,255,255,0.05)"
                  : "rgba(255,255,255,0.12)"
                : idx % 2 === 0
                ? "rgba(0,0,0,0.03)"
                : "rgba(0,0,0,0.08)";
              const hoverColor = dark
                ? "rgba(255,255,255,0.25)"
                : "rgba(0,0,0,0.15)";

              return (
                <tr
                  key={getRowKey(e, idx)}
                  className="fade-in-row"
                  style={{
                    background: baseColor,
                    transition: "background 0.25s ease, opacity 0.6s ease",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(ev) =>
                    (ev.currentTarget.style.background = hoverColor)
                  }
                  onMouseLeave={(ev) =>
                    (ev.currentTarget.style.background = baseColor)
                  }
                >
                  <Td title={ts || ""}>{ts ? timeAgo(ts) : "—"}</Td>
                  <Td mono>{safe(e, "src_ip", e.ip || "—")}</Td>
                  <Td mono>{safe(e, "dst_ip", "—")}</Td>
                  <Td>{safe(e, "type", safe(e, "event_type", "—"))}</Td>
                  <Td>
                    <span className="inline-flex items-center gap-2">
                      <Flag code={safe(e, "geoip.country_code", "").toUpperCase()} />
                      {safe(e, "geoip.country_name", "—")}
                    </span>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Local keyframes + compact cell padding + fadeIn --------------------- */}
      <style>{`
        @keyframes fadeInRow { from { opacity: 0; transform: translateY(2px);} to { opacity: 1; transform: translateY(0);} }
        .fade-in-row { animation: fadeInRow 0.4s ease forwards; }
        td, th { padding: 0.6rem 0.9rem; }
      `}</style>
    </div>
  );
}

// --- Helpers ---------------------------------------------------------------
function Th({ children }) {
  return (
    <th className="text-left font-medium uppercase tracking-wide text-xs py-2 px-3">
      {children}
    </th>
  );
}

function Td({ children, mono }) {
  return (
    <td className={`py-2 px-3 ${mono ? "font-mono text-[13px]" : ""}`}>
      {children}
    </td>
  );
}

function Flag({ code }) {
  if (!code || code.length !== 2) return <span className="opacity-50">—</span>;
  const a = 0x1f1e6 - "A".charCodeAt(0);
  const emoji = String.fromCodePoint(
    code.charCodeAt(0) + a,
    code.charCodeAt(1) + a
  );
  return (
    <span title={code} aria-label={`flag ${code}`} className="text-lg leading-none">
      {emoji}
    </span>
  );
}
