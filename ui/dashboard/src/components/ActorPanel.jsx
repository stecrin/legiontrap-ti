import { Fragment, useEffect, useState } from "react";
import { getActors, getActorStability, getActorSuggestions } from "../lib/api";
import { timeAgo } from "../utils/format";

const REFRESH_MS = 30_000;

// ---------- shared helpers ----------

function actorStatusColor(status) {
  switch (status) {
    case "active": return "#22c55e";
    case "archived": return "#6b7280";
    default: return "#9ca3af";
  }
}

function campaignStatusColor(status) {
  switch (status) {
    case "active": return "#22c55e";
    case "reactivated": return "#f97316";
    case "dormant": return "#60a5fa";
    case "historical": return "#6b7280";
    default: return "#9ca3af";
  }
}

function StatusBadge({ status, colorFn }) {
  const color = colorFn(status);
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

const REL_TYPE_COLORS = {
  primary_campaign: "#818cf8",
  infrastructure_reuse: "#f59e0b",
  tactic_match: "#34d399",
  temporal_overlap: "#60a5fa",
};

function RelTypeBadge({ type }) {
  if (!type) return <span style={{ opacity: 0.4 }}>—</span>;
  const color = REL_TYPE_COLORS[type] ?? "#9ca3af";
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
      {type.replace(/_/g, " ")}
    </span>
  );
}

function ScoreBar({ value, dark }) {
  if (value == null) return <span style={{ opacity: 0.4 }}>—</span>;
  const pct = Math.round(value * 100);
  const color = pct >= 90 ? "#22c55e" : pct >= 70 ? "#f59e0b" : "#9ca3af";
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
        <span style={{ display: "block", width: `${pct}%`, height: "100%", background: color, borderRadius: 3 }} />
      </span>
      <span style={{ fontFamily: "monospace", fontSize: 12, color }}>{pct}%</span>
    </span>
  );
}

function StabilityStatusLabel({ status }) {
  const map = {
    ok: { label: "ok", color: "#22c55e" },
    no_linked_campaigns: { label: "no campaigns", color: "#6b7280" },
    no_stability_data: { label: "no data", color: "#9ca3af" },
    partial_data: { label: "partial", color: "#f59e0b" },
  };
  const { label, color } = map[status] ?? { label: status ?? "—", color: "#9ca3af" };
  return <span style={{ fontSize: 11, fontWeight: 600, color }}>{label}</span>;
}

// ---------- Actor Detail (expanded row) ----------

function ActorDetail({ actorId, actor, dark }) {
  const [stability, setStability] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const border = dark ? "#374151" : "#e5e7eb";
  const fg = dark ? "#d1d5db" : "#374151";

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getActorStability(actorId)
      .then((data) => { if (!cancelled) { setStability(data); setLoading(false); } })
      .catch((e) => { if (!cancelled) { setError(e.message); setLoading(false); } });
    return () => { cancelled = true; };
  }, [actorId]);

  if (loading) return <span style={{ opacity: 0.5, fontSize: 13 }}>Loading…</span>;
  if (error) return <span style={{ color: "#ef4444", fontSize: 13 }}>Error: {error}</span>;
  if (!stability) return null;

  const dims = stability.dimension_stability ?? {};
  const dimKeys = Object.keys(dims);
  const agg = stability.actor_composite_stability;
  const contributors = stability.contributors ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, fontSize: 13, color: fg }}>
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        {actor.notes && (
          <div style={{ flex: "1 1 260px" }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 2 }}>Notes</div>
            <div style={{ opacity: 0.85 }}>{actor.notes}</div>
          </div>
        )}
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 2 }}>Stability</div>
          <StabilityStatusLabel status={stability.status} />
        </div>
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 2 }}>Linked Campaigns</div>
          <div style={{ fontFamily: "monospace" }}>{stability.linked_campaign_count}</div>
        </div>
        {agg && (
          <div>
            <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 2 }}>Composite Stability</div>
            <div style={{ fontFamily: "monospace" }}>
              <span style={{ color: "#22c55e" }}>{(agg.mean * 100).toFixed(1)}%</span>
              <span style={{ opacity: 0.5, fontSize: 11, marginLeft: 4 }}>
                ({(agg.min * 100).toFixed(0)}–{(agg.max * 100).toFixed(0)}%)
              </span>
            </div>
          </div>
        )}
      </div>

      {dimKeys.length > 0 && (
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 6 }}>
            Dimension Stability
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {dimKeys.map((dim) => {
              const d = dims[dim];
              return (
                <div key={dim} style={{
                  padding: "6px 10px",
                  borderRadius: 8,
                  border: `1px solid ${border}`,
                  fontSize: 12,
                  minWidth: 90,
                }}>
                  <div style={{ fontSize: 10, textTransform: "uppercase", opacity: 0.55, marginBottom: 2 }}>{dim}</div>
                  <div style={{ fontFamily: "monospace" }}>
                    <span style={{ fontWeight: 600 }}>{(d.mean * 100).toFixed(1)}%</span>
                    <span style={{ opacity: 0.5, fontSize: 10, marginLeft: 3 }}>
                      ({(d.min * 100).toFixed(0)}–{(d.max * 100).toFixed(0)})
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {contributors.length > 0 ? (
        <div>
          <div style={{ fontSize: 11, textTransform: "uppercase", opacity: 0.55, marginBottom: 6 }}>
            Linked Campaigns ({contributors.length})
          </div>
          <div style={{ borderRadius: 8, border: `1px solid ${border}`, overflow: "hidden" }}>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: dark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)" }}>
                  {["Campaign", "Relationship", "Composite", "Samples", "Last Computed"].map((h) => (
                    <th key={h} style={{
                      padding: "4px 10px",
                      textAlign: "left",
                      fontSize: 10,
                      fontWeight: 600,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                      opacity: 0.7,
                      whiteSpace: "nowrap",
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {contributors.map((c, i) => (
                  <tr key={c.campaign_id} style={{ borderTop: i > 0 ? `1px solid ${border}` : "none" }}>
                    <td style={{ padding: "4px 10px", fontFamily: "monospace" }}>
                      {c.campaign_name ?? c.campaign_id}
                    </td>
                    <td style={{ padding: "4px 10px" }}>
                      <RelTypeBadge type={c.relationship_type} />
                    </td>
                    <td style={{ padding: "4px 10px" }}>
                      <ScoreBar value={c.composite_score} dark={dark} />
                    </td>
                    <td style={{ padding: "4px 10px", fontFamily: "monospace" }}>
                      {c.sample_count ?? "—"}
                    </td>
                    <td style={{ padding: "4px 10px", fontFamily: "monospace", fontSize: 11 }}>
                      {c.last_computed ? timeAgo(c.last_computed) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div style={{ opacity: 0.5, fontSize: 12 }}>No linked campaigns.</div>
      )}
    </div>
  );
}

// ---------- Main component ----------

export default function ActorPanel({ dark }) {
  const [actors, setActors] = useState([]);
  const [actorsLoading, setActorsLoading] = useState(true);
  const [actorsOnline, setActorsOnline] = useState(true);
  const [expandedId, setExpandedId] = useState(null);

  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(true);
  const [dismissedKeys, setDismissedKeys] = useState(new Set());
  const [suggMeta, setSuggMeta] = useState(null);

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

  async function fetchActors() {
    try {
      const data = await getActors();
      setActors(data.items ?? []);
      setActorsOnline(true);
    } catch (e) {
      console.error("Actors fetch:", e);
      setActorsOnline(false);
    } finally {
      setActorsLoading(false);
    }
  }

  async function fetchSuggestions() {
    try {
      const data = await getActorSuggestions();
      setSuggestions(data.suggestions ?? []);
      setSuggMeta({
        count: data.count,
        total_pairs_evaluated: data.total_pairs_evaluated,
        min_score_applied: data.min_score_applied,
        campaigns_evaluated: data.campaigns_evaluated,
      });
    } catch (e) {
      console.error("Suggestions fetch:", e);
    } finally {
      setSuggestionsLoading(false);
    }
  }

  useEffect(() => {
    fetchActors();
    fetchSuggestions();
    const t = setInterval(() => { fetchActors(); fetchSuggestions(); }, REFRESH_MS);
    return () => clearInterval(t);
  }, []);

  function toggleRow(id) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  function dismissSuggestion(key) {
    setDismissedKeys((prev) => new Set([...prev, key]));
  }

  const visibleSuggestions = suggestions.filter(
    (s) => !dismissedKeys.has(`${s.campaign_a.id}-${s.campaign_b.id}`)
  );

  return (
    <div style={{ color: fg }}>

      {/* === Actor Profiles === */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Actor Profiles</h2>
        <span style={{ fontSize: 12, opacity: 0.6 }}>
          {actorsOnline
            ? actorsLoading
              ? "Loading…"
              : `${actors.length} profile${actors.length !== 1 ? "s" : ""}`
            : "Offline"}
        </span>
      </div>

      <div style={{ borderRadius: 12, border: `1px solid ${border}`, overflow: "hidden", background: cardBg }}>
        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: dark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)" }}>
              <th style={th}>Display Name</th>
              <th style={th}>Status</th>
              <th style={th}>Confidence</th>
              <th style={th}>Notes</th>
              <th style={th}>Created</th>
              <th style={th}>Updated</th>
            </tr>
          </thead>
          <tbody>
            {actors.length === 0 && !actorsLoading && (
              <tr>
                <td colSpan={6} style={{ ...td, textAlign: "center", opacity: 0.5 }}>
                  No actor profiles defined.
                </td>
              </tr>
            )}
            {actors.map((actor, idx) => {
              const isExpanded = expandedId === actor.id;
              const evenBg = dark ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.01)";
              const oddBg = dark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.04)";
              const rowBg = idx % 2 === 0 ? evenBg : oddBg;
              const hoverBg = dark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.09)";

              return (
                <Fragment key={actor.id}>
                  <tr
                    onClick={() => toggleRow(actor.id)}
                    style={{
                      background: rowBg,
                      cursor: "pointer",
                      borderTop: idx > 0 ? `1px solid ${border}` : "none",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = hoverBg)}
                    onMouseLeave={(e) => (e.currentTarget.style.background = rowBg)}
                  >
                    <td style={{ ...td, fontFamily: "monospace", fontWeight: 600 }}>
                      {actor.display_name}
                      <span style={{ marginLeft: 6, fontSize: 10, opacity: 0.45 }}>
                        {isExpanded ? "▲" : "▼"}
                      </span>
                    </td>
                    <td style={td}>
                      <StatusBadge status={actor.status} colorFn={actorStatusColor} />
                    </td>
                    <td style={td}><ScoreBar value={actor.confidence} dark={dark} /></td>
                    <td style={{
                      ...td,
                      fontSize: 12,
                      opacity: actor.notes ? 0.75 : 0.35,
                      fontStyle: actor.notes ? "normal" : "italic",
                      maxWidth: 220,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}>
                      {actor.notes
                        ? actor.notes.length > 60
                          ? actor.notes.slice(0, 60) + "…"
                          : actor.notes
                        : "no notes"}
                    </td>
                    <td style={{ ...td, fontFamily: "monospace", fontSize: 12 }}>
                      {actor.created_at ? timeAgo(actor.created_at) : "—"}
                    </td>
                    <td style={{ ...td, fontFamily: "monospace", fontSize: 12 }}>
                      {actor.updated_at ? timeAgo(actor.updated_at) : "—"}
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr style={{ borderTop: `1px solid ${border}` }}>
                      <td colSpan={6} style={{
                        padding: "14px 16px",
                        background: dark ? "rgba(99,102,241,0.06)" : "rgba(99,102,241,0.03)",
                        borderBottom: `1px solid ${border}`,
                      }}>
                        <ActorDetail actorId={actor.id} actor={actor} dark={dark} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* === Review Candidates (Suggestions) === */}
      <div style={{ marginTop: 32 }}>
        <div style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          marginBottom: 10,
        }}>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>Review Candidates</h2>
            <p style={{ fontSize: 12, opacity: 0.6, margin: "4px 0 0" }}>
              Suggested campaign pairs for operator review only. No automatic action is taken.
              {suggMeta && (
                <span style={{ marginLeft: 6 }}>
                  {suggMeta.campaigns_evaluated} campaigns evaluated · threshold {Math.round(suggMeta.min_score_applied * 100)}%
                </span>
              )}
            </p>
          </div>
          {visibleSuggestions.length > 0 && (
            <span style={{
              marginTop: 2,
              padding: "2px 10px",
              borderRadius: 9999,
              fontSize: 11,
              fontWeight: 600,
              background: "rgba(251,191,36,0.15)",
              color: "#f59e0b",
              whiteSpace: "nowrap",
            }}>
              {visibleSuggestions.length} candidate{visibleSuggestions.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        <div style={{ borderRadius: 12, border: `1px solid ${border}`, overflow: "hidden", background: cardBg }}>
          {suggestionsLoading ? (
            <div style={{ padding: 16, opacity: 0.5, fontSize: 13 }}>Loading suggestions…</div>
          ) : visibleSuggestions.length === 0 ? (
            <div style={{ padding: 16, opacity: 0.5, fontSize: 13 }}>
              No review candidates above threshold.
            </div>
          ) : (
            <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ background: dark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)" }}>
                  <th style={th}>Campaign A</th>
                  <th style={th}>Campaign B</th>
                  <th style={th}>Score</th>
                  <th style={th}>Suggested Candidate</th>
                  <th style={th}>Breakdown</th>
                  <th style={{ ...th, width: 60 }}></th>
                </tr>
              </thead>
              <tbody>
                {visibleSuggestions.map((s, idx) => {
                  const key = `${s.campaign_a.id}-${s.campaign_b.id}`;
                  const pct = Math.round((s.similarity_score ?? 0) * 100);
                  const scoreColor = pct >= 90 ? "#22c55e" : pct >= 80 ? "#f59e0b" : "#9ca3af";
                  const breakdown = s.score_breakdown ?? {};

                  return (
                    <tr key={key} style={{ borderTop: idx > 0 ? `1px solid ${border}` : "none" }}>
                      <td style={{ padding: "8px 10px" }}>
                        <div style={{ fontFamily: "monospace", fontWeight: 600, fontSize: 12 }}>
                          {s.campaign_a.name}
                        </div>
                        <StatusBadge status={s.campaign_a.status} colorFn={campaignStatusColor} />
                      </td>
                      <td style={{ padding: "8px 10px" }}>
                        <div style={{ fontFamily: "monospace", fontWeight: 600, fontSize: 12 }}>
                          {s.campaign_b.name}
                        </div>
                        <StatusBadge status={s.campaign_b.status} colorFn={campaignStatusColor} />
                      </td>
                      <td style={{ padding: "8px 10px" }}>
                        <span style={{ fontFamily: "monospace", fontWeight: 700, color: scoreColor, fontSize: 15 }}>
                          {pct}%
                        </span>
                      </td>
                      <td style={{ padding: "8px 10px" }}>
                        <RelTypeBadge type={s.suggested_relationship_type} />
                        <div style={{ fontSize: 10, opacity: 0.5, marginTop: 3 }}>
                          possible relationship · operator review required
                        </div>
                      </td>
                      <td style={{ padding: "8px 10px", fontSize: 11, fontFamily: "monospace", opacity: 0.7 }}>
                        {Object.entries(breakdown)
                          .filter(([k, v]) => v != null && k !== "weighted_total")
                          .map(([k, v]) => (
                            <div key={k}>{k.replace("_similarity", "")}: {(v * 100).toFixed(0)}%</div>
                          ))}
                      </td>
                      <td style={{ padding: "8px 10px" }}>
                        <button
                          onClick={() => dismissSuggestion(key)}
                          title="Dismiss from view — no server action taken"
                          style={{
                            padding: "3px 8px",
                            borderRadius: 6,
                            border: `1px solid ${border}`,
                            background: "transparent",
                            color: dark ? "#9ca3af" : "#6b7280",
                            fontSize: 11,
                            cursor: "pointer",
                          }}
                        >
                          Dismiss
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {visibleSuggestions.length > 0 && (
            <div style={{
              padding: "6px 12px",
              fontSize: 11,
              opacity: 0.4,
              borderTop: `1px solid ${border}`,
              fontStyle: "italic",
            }}>
              These are suggested candidates only. No campaigns are linked automatically. Dismiss removes from this view only.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
