import { useEffect, useState } from "react";
import { getTopASNs } from "../lib/api";
import { timeAgo } from "../utils/format";

const REFRESH_MS = 30_000;

export default function TopASNs({ dark }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);

  const cardBg = dark ? "#111827" : "#f9fafb";
  const border = dark ? "#374151" : "#d1d5db";
  const fg = dark ? "#e5e7eb" : "#111827";
  const th = {
    padding: "0.5rem 0.8rem",
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  };
  const td = { padding: "0.55rem 0.8rem" };

  async function fetchData() {
    try {
      const data = await getTopASNs(Date.now());
      setItems(data.items ?? []);
      setOnline(true);
      setLastUpdated(new Date());
    } catch (e) {
      console.error("TopASNs fetch:", e);
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchData();
    const t = setInterval(fetchData, REFRESH_MS);
    return () => clearInterval(t);
  }, []);

  return (
    <div style={{ color: fg }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 10,
        }}
      >
        <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Top ASNs</h2>
        <span style={{ fontSize: 12, opacity: 0.6 }}>
          {online
            ? lastUpdated
              ? `Updated ${timeAgo(lastUpdated)}`
              : "Loading…"
            : "Offline"}
        </span>
      </div>

      <div
        style={{
          borderRadius: 12,
          border: `1px solid ${border}`,
          overflow: "hidden",
          background: cardBg,
        }}
      >
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr
              style={{
                background: dark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)",
              }}
            >
              <th style={{ ...th, textAlign: "left" }}>ASN</th>
              <th style={{ ...th, textAlign: "left" }}>Organization</th>
              <th style={{ ...th, textAlign: "right" }}>Events</th>
              <th style={{ ...th, textAlign: "right" }}>Unique IPs</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !loading && (
              <tr>
                <td colSpan={4} style={{ ...td, textAlign: "center", opacity: 0.5 }}>
                  No ASN data yet.
                </td>
              </tr>
            )}
            {items.map((item, idx) => {
              const evenBg = dark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.01)";
              const oddBg = dark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.04)";
              return (
                <tr
                  key={item.asn}
                  style={{
                    background: idx % 2 === 0 ? evenBg : oddBg,
                    borderTop: idx > 0 ? `1px solid ${border}` : "none",
                  }}
                >
                  <td style={{ ...td, fontFamily: "monospace", fontWeight: 600 }}>
                    AS{item.asn}
                  </td>
                  <td style={td}>{item.asn_org ?? "—"}</td>
                  <td style={{ ...td, textAlign: "right", fontWeight: 600 }}>
                    {item.event_count ?? "—"}
                  </td>
                  <td style={{ ...td, textAlign: "right" }}>{item.unique_ips ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
