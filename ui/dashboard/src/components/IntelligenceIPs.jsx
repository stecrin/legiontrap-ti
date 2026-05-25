import { Fragment, useEffect, useState } from "react";
import { getIntelligenceIPs, getIntelligenceIP } from "../lib/api";
import { timeAgo } from "../utils/format";

const REFRESH_MS = 30_000;

function scoreColor(score) {
  if (score == null) return "#9ca3af";
  if (score >= 70) return "#ef4444";
  if (score >= 40) return "#f97316";
  return "#22c55e";
}

function Flag({ code }) {
  if (!code || code.length !== 2) return <span style={{ opacity: 0.4 }}>—</span>;
  const a = 0x1f1e6 - "A".charCodeAt(0);
  return (
    <span title={code}>
      {String.fromCodePoint(code.charCodeAt(0) + a, code.charCodeAt(1) + a)}
    </span>
  );
}

function TagList({ tags, dark }) {
  if (!tags || tags.length === 0) return <span style={{ opacity: 0.4 }}>—</span>;
  return (
    <span style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
      {tags.map((tag) => (
        <span
          key={tag}
          style={{
            padding: "1px 7px",
            borderRadius: 9999,
            fontSize: 11,
            fontWeight: 600,
            background: dark ? "rgba(239,68,68,0.2)" : "rgba(239,68,68,0.12)",
            color: dark ? "#fca5a5" : "#b91c1c",
          }}
        >
          {tag}
        </span>
      ))}
    </span>
  );
}

function IPProfile({ profile, dark }) {
  const fg = dark ? "#d1d5db" : "#374151";
  const chipBg = dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.07)";
  const entries = Object.entries(profile.event_type_breakdown ?? {});

  return (
    <div style={{ display: "flex", gap: 28, flexWrap: "wrap", fontSize: 13, color: fg }}>
      <div>
        <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 3 }}>
          First Seen
        </div>
        <div style={{ fontFamily: "monospace" }}>
          {profile.first_seen ? timeAgo(profile.first_seen) : "—"}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 3 }}>
          Last Seen
        </div>
        <div style={{ fontFamily: "monospace" }}>
          {profile.last_seen ? timeAgo(profile.last_seen) : "—"}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 3 }}>
          Score
        </div>
        <div style={{ fontWeight: 700, color: scoreColor(profile.reputation_score) }}>
          {profile.reputation_score ?? "—"}
        </div>
      </div>
      {entries.length > 0 && (
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 3 }}>
            Event Breakdown
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {entries.map(([type, count]) => (
              <span
                key={type}
                style={{
                  padding: "2px 8px",
                  borderRadius: 6,
                  background: chipBg,
                  fontSize: 12,
                  fontFamily: "monospace",
                }}
              >
                {type}: {count}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function IntelligenceIPs({ dark }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [expandedIp, setExpandedIp] = useState(null);
  const [profiles, setProfiles] = useState({});
  const [profileLoading, setProfileLoading] = useState(null);

  const cardBg = dark ? "#111827" : "#f9fafb";
  const border = dark ? "#374151" : "#d1d5db";
  const fg = dark ? "#e5e7eb" : "#111827";
  const th = {
    padding: "0.5rem 0.8rem",
    textAlign: "left",
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    whiteSpace: "nowrap",
  };
  const td = { padding: "0.55rem 0.8rem" };

  async function fetchList() {
    try {
      const data = await getIntelligenceIPs(Date.now());
      setItems(data.items ?? []);
      setOnline(true);
      setLastUpdated(new Date());
    } catch (e) {
      console.error("IntelligenceIPs fetch:", e);
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }

  async function toggleRow(ip) {
    if (expandedIp === ip) {
      setExpandedIp(null);
      return;
    }
    setExpandedIp(ip);
    if (profiles[ip]) return;
    setProfileLoading(ip);
    try {
      const profile = await getIntelligenceIP(ip);
      setProfiles((prev) => ({ ...prev, [ip]: profile }));
    } catch (e) {
      console.error("IntelligenceIP profile fetch:", e);
    } finally {
      setProfileLoading(null);
    }
  }

  useEffect(() => {
    fetchList();
    const t = setInterval(fetchList, REFRESH_MS);
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
        <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Top Source IPs</h2>
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
              <th style={th}>IP</th>
              <th style={th}>Score</th>
              <th style={th}>Events</th>
              <th style={th}>Country</th>
              <th style={th}>ASN / Org</th>
              <th style={th}>Tags</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !loading && (
              <tr>
                <td colSpan={6} style={{ ...td, textAlign: "center", opacity: 0.5 }}>
                  No intelligence data yet.
                </td>
              </tr>
            )}
            {items.map((item, idx) => {
              const isExpanded = expandedIp === item.ip;
              const evenBg = dark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.01)";
              const oddBg = dark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.04)";
              const rowBg = idx % 2 === 0 ? evenBg : oddBg;
              const hoverBg = dark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.09)";
              const profile = profiles[item.ip];

              return (
                <Fragment key={item.ip}>
                  <tr
                    onClick={() => toggleRow(item.ip)}
                    style={{
                      background: rowBg,
                      cursor: "pointer",
                      borderTop: idx > 0 ? `1px solid ${border}` : "none",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = hoverBg)}
                    onMouseLeave={(e) => (e.currentTarget.style.background = rowBg)}
                  >
                    <td style={{ ...td, fontFamily: "monospace", fontWeight: 500 }}>
                      {item.ip}
                      <span style={{ marginLeft: 6, fontSize: 10, opacity: 0.45 }}>
                        {isExpanded ? "▲" : "▼"}
                      </span>
                    </td>
                    <td
                      style={{
                        ...td,
                        fontWeight: 700,
                        color: scoreColor(item.reputation_score),
                      }}
                    >
                      {item.reputation_score ?? "—"}
                    </td>
                    <td style={td}>{item.event_count ?? "—"}</td>
                    <td style={td}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                        <Flag code={item.country_code} />
                        <span>{item.country_name ?? "—"}</span>
                      </span>
                    </td>
                    <td style={{ ...td, fontFamily: "monospace", fontSize: 12 }}>
                      {item.asn ? (
                        <>
                          <span style={{ opacity: 0.65 }}>AS{item.asn}</span>
                          {item.asn_org && (
                            <span style={{ marginLeft: 6 }}>{item.asn_org}</span>
                          )}
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td style={td}>
                      <TagList tags={item.tags} dark={dark} />
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr style={{ borderTop: `1px solid ${border}` }}>
                      <td
                        colSpan={6}
                        style={{
                          padding: "12px 16px",
                          background: dark
                            ? "rgba(99,102,241,0.07)"
                            : "rgba(99,102,241,0.04)",
                          borderBottom: `1px solid ${border}`,
                        }}
                      >
                        {profileLoading === item.ip ? (
                          <span style={{ opacity: 0.5, fontSize: 13 }}>
                            Loading profile…
                          </span>
                        ) : profile ? (
                          <IPProfile profile={profile} dark={dark} />
                        ) : (
                          <span style={{ opacity: 0.5, fontSize: 13 }}>
                            Profile unavailable.
                          </span>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
