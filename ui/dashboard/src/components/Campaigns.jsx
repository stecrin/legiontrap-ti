import { Fragment, useEffect, useState } from "react";
import { getCampaigns, getCampaignDetail, postCampaignSummary } from "../lib/api";
import { timeAgo } from "../utils/format";
import CampaignAiPanel from "./CampaignAiPanel";
import CampaignAiOutputHistory from "./CampaignAiOutputHistory";

const REFRESH_MS = 30_000;

function statusColor(status) {
  switch (status) {
    case "active": return "#22c55e";
    case "reactivated": return "#f97316";
    case "dormant": return "#60a5fa";
    case "historical": return "#6b7280";
    default: return "#9ca3af";
  }
}

function StatusBadge({ status }) {
  const color = statusColor(status);
  return (
    <span style={{
      padding: "2px 8px",
      borderRadius: 9999,
      fontSize: 11,
      fontWeight: 600,
      background: `${color}22`,
      color,
      textTransform: "uppercase",
      letterSpacing: "0.04em",
    }}>
      {status ?? "—"}
    </span>
  );
}

function ConfidenceBar({ value, dark }) {
  if (value == null) return <span style={{ opacity: 0.4 }}>—</span>;
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "#ef4444" : pct >= 60 ? "#f97316" : "#22c55e";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{
        display: "inline-block",
        width: 48,
        height: 6,
        borderRadius: 3,
        background: dark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)",
        overflow: "hidden",
      }}>
        <span style={{
          display: "block",
          width: `${pct}%`,
          height: "100%",
          background: color,
          borderRadius: 3,
        }} />
      </span>
      <span style={{ fontFamily: "monospace", fontSize: 12, color }}>{pct}%</span>
    </span>
  );
}

function evidenceQualityColor(q) {
  switch (q) {
    case "mature": return "#22c55e";
    case "established": return "#60a5fa";
    case "emerging": return "#f59e0b";
    case "sparse": return "#6b7280";
    default: return "#9ca3af";
  }
}

function EvidenceQualityBadge({ quality }) {
  if (!quality) return null;
  const color = evidenceQualityColor(quality);
  return (
    <span style={{
      padding: "2px 7px",
      borderRadius: 9999,
      fontSize: 10,
      fontWeight: 600,
      background: `${color}22`,
      color,
      textTransform: "uppercase",
      letterSpacing: "0.04em",
    }}>
      {quality}
    </span>
  );
}

function ExplainSummary({ notes, dark }) {
  if (!notes) return null;
  let parsed;
  try { parsed = JSON.parse(notes); } catch { return null; }
  const score = parsed.weighted_total;
  const dims = parsed.dimensions_used;
  const decision = parsed.decision;
  if (score == null) return null;
  const label = decision?.replace(/_/g, " ") ?? "—";
  const fg = dark ? "#9ca3af" : "#6b7280";
  return (
    <span style={{ fontSize: 11, color: fg, fontFamily: "monospace" }}>
      sim {(score * 100).toFixed(1)}%
      {dims != null && <span style={{ marginLeft: 4 }}>({dims}d)</span>}
      {" · "}
      <span style={{ color: decision === "automatic_association" ? "#22c55e" : "#f97316" }}>
        {label}
      </span>
    </span>
  );
}

function CampaignDetail({ detail, dark }) {
  const fg = dark ? "#d1d5db" : "#374151";
  const border = dark ? "#374151" : "#e5e7eb";

  const observations = detail.observations ?? [];
  const members = detail.members ?? [];
  const recent = observations.slice().reverse().slice(0, 5);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, fontSize: 13, color: fg }}>
      {/* Summary row */}
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 2 }}>First Seen</div>
          <div style={{ fontFamily: "monospace" }}>{detail.first_seen ? timeAgo(detail.first_seen) : "—"}</div>
        </div>
        {detail.dormant_since && (
          <div>
            <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 2 }}>Dormant Since</div>
            <div style={{ fontFamily: "monospace" }}>{timeAgo(detail.dormant_since)}</div>
          </div>
        )}
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 2 }}>Members</div>
          <div style={{ fontFamily: "monospace" }}>{members.length}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 2 }}>Total Observations</div>
          <div style={{ fontFamily: "monospace" }}>{observations.length}</div>
        </div>
      </div>

      {/* Recent observations */}
      {recent.length > 0 && (
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 6 }}>
            Recent Observations
          </div>
          <div style={{
            borderRadius: 8,
            border: `1px solid ${border}`,
            overflow: "hidden",
          }}>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: dark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)" }}>
                  {["When", "Source IP", "Events", "Flags", "Similarity"].map((h) => (
                    <th key={h} style={{
                      padding: "4px 10px",
                      textAlign: "left",
                      fontSize: 11,
                      fontWeight: 600,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                      whiteSpace: "nowrap",
                      opacity: 0.7,
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recent.map((obs, i) => (
                  <tr key={obs.id} style={{
                    borderTop: i > 0 ? `1px solid ${border}` : "none",
                  }}>
                    <td style={{ padding: "4px 10px", fontFamily: "monospace", whiteSpace: "nowrap" }}>
                      {timeAgo(obs.observed_at)}
                    </td>
                    <td style={{ padding: "4px 10px", fontFamily: "monospace" }}>{obs.source_ip}</td>
                    <td style={{ padding: "4px 10px" }}>{obs.event_count ?? "—"}</td>
                    <td style={{ padding: "4px 10px" }}>
                      {obs.is_reactivation && (
                        <span style={{
                          padding: "1px 6px",
                          borderRadius: 9999,
                          fontSize: 10,
                          fontWeight: 700,
                          background: "rgba(249,115,22,0.15)",
                          color: "#f97316",
                          textTransform: "uppercase",
                        }}>
                          reactivation
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "4px 10px" }}>
                      <ExplainSummary notes={obs.notes} dark={dark} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Campaigns({ dark }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [expandedId, setExpandedId] = useState(null);
  const [details, setDetails] = useState({});
  const [detailLoading, setDetailLoading] = useState(null);
  const [aiSummaries, setAiSummaries] = useState({});

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
      const data = await getCampaigns(Date.now());
      setItems(data.items ?? []);
      setOnline(true);
      setLastUpdated(new Date());
    } catch (e) {
      console.error("Campaigns fetch:", e);
      setOnline(false);
    } finally {
      setLoading(false);
    }
  }

  async function toggleRow(id) {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    if (details[id]) return;
    setDetailLoading(id);
    try {
      const detail = await getCampaignDetail(id);
      setDetails((prev) => ({ ...prev, [id]: detail }));
    } catch (e) {
      console.error("Campaign detail fetch:", e);
    } finally {
      setDetailLoading(null);
    }
  }

  async function generateSummary(campaignId) {
    setAiSummaries((prev) => ({
      ...prev,
      [campaignId]: { status: "loading", data: null, errorMsg: null },
    }));
    try {
      const { status, data } = await postCampaignSummary(campaignId);
      if (status === 200) {
        setAiSummaries((prev) => ({
          ...prev,
          [campaignId]: { status: "success", data, errorMsg: null },
        }));
      } else {
        const msg =
          data?.detail ??
          (status === 503
            ? "AI features are currently unavailable."
            : status === 422
              ? "AI summary unavailable (configuration conflict)."
              : "AI summary unavailable.");
        setAiSummaries((prev) => ({
          ...prev,
          [campaignId]: { status: "error", data: null, errorMsg: msg },
        }));
      }
    } catch {
      setAiSummaries((prev) => ({
        ...prev,
        [campaignId]: { status: "error", data: null, errorMsg: "Network error. AI summary unavailable." },
      }));
    }
  }

  function dismissSummary(campaignId) {
    setAiSummaries((prev) => ({
      ...prev,
      [campaignId]: { status: "idle", data: null, errorMsg: null },
    }));
  }

  useEffect(() => {
    fetchList();
    const t = setInterval(fetchList, REFRESH_MS);
    return () => clearInterval(t);
  }, []);

  return (
    <div style={{ color: fg }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Campaigns</h2>
        <span style={{ fontSize: 12, opacity: 0.6 }}>
          {online
            ? lastUpdated
              ? `Updated ${timeAgo(lastUpdated)}`
              : "Loading…"
            : "Offline"}
        </span>
      </div>

      <div style={{ borderRadius: 12, border: `1px solid ${border}`, overflow: "hidden", background: cardBg }}>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: dark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)" }}>
              <th style={th}>Name</th>
              <th style={th}>Status</th>
              <th style={th}>Quality</th>
              <th style={th}>Confidence</th>
              <th style={th}>Members</th>
              <th style={th}>Last Seen</th>
              <th style={th}>Reactivations</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !loading && (
              <tr>
                <td colSpan={7} style={{ ...td, textAlign: "center", opacity: 0.5 }}>
                  No campaigns detected yet.
                </td>
              </tr>
            )}
            {items.map((item, idx) => {
              const isExpanded = expandedId === item.id;
              const evenBg = dark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.01)";
              const oddBg = dark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.04)";
              const rowBg = idx % 2 === 0 ? evenBg : oddBg;
              const hoverBg = dark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.09)";
              const detail = details[item.id];

              return (
                <Fragment key={item.id}>
                  <tr
                    onClick={() => toggleRow(item.id)}
                    style={{
                      background: rowBg,
                      cursor: "pointer",
                      borderTop: idx > 0 ? `1px solid ${border}` : "none",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = hoverBg)}
                    onMouseLeave={(e) => (e.currentTarget.style.background = rowBg)}
                  >
                    <td style={{ ...td, fontFamily: "monospace", fontWeight: 600 }}>
                      {item.name}
                      <span style={{ marginLeft: 6, fontSize: 10, opacity: 0.45 }}>
                        {isExpanded ? "▲" : "▼"}
                      </span>
                    </td>
                    <td style={td}><StatusBadge status={item.status} /></td>
                    <td style={td}><EvidenceQualityBadge quality={item.evidence_quality} /></td>
                    <td style={td}><ConfidenceBar value={item.confidence} dark={dark} /></td>
                    <td style={{ ...td, fontFamily: "monospace" }}>{item.member_ip_count ?? "—"}</td>
                    <td style={{ ...td, fontFamily: "monospace", fontSize: 12 }}>
                      {item.last_seen ? timeAgo(item.last_seen) : "—"}
                    </td>
                    <td style={{ ...td, fontFamily: "monospace" }}>
                      {item.reactivation_count > 0
                        ? <span style={{ color: "#f97316", fontWeight: 600 }}>{item.reactivation_count}</span>
                        : <span style={{ opacity: 0.4 }}>0</span>
                      }
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr style={{ borderTop: `1px solid ${border}` }}>
                      <td colSpan={7} style={{
                        padding: "14px 16px",
                        background: dark ? "rgba(99,102,241,0.06)" : "rgba(99,102,241,0.03)",
                        borderBottom: `1px solid ${border}`,
                      }}>
                        {detailLoading === item.id ? (
                          <span style={{ opacity: 0.5, fontSize: 13 }}>Loading detail…</span>
                        ) : detail ? (
                          <CampaignDetail detail={detail} dark={dark} />
                        ) : (
                          <span style={{ opacity: 0.5, fontSize: 13 }}>Detail unavailable.</span>
                        )}
                        <CampaignAiPanel
                          summaryState={aiSummaries[item.id] ?? { status: "idle", data: null, errorMsg: null }}
                          onGenerate={() => generateSummary(item.id)}
                          onDismiss={() => dismissSummary(item.id)}
                          dark={dark}
                        />
                        <CampaignAiOutputHistory
                          campaignId={item.id}
                          dark={dark}
                        />
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
