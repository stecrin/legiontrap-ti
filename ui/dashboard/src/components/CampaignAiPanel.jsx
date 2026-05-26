/**
 * CampaignAiPanel — operator-triggered AI summary panel for a single campaign.
 *
 * Rendering rules (Phase 5 §8):
 *   - AI summary is NEVER auto-generated; operator must click "Generate AI Summary"
 *   - Warning/disclaimer label is always visible, not dismissible
 *   - Deterministic data panel (rendered by parent) appears above this panel
 *   - AI output is always plain text — never HTML, never dangerouslySetInnerHTML
 *   - No output is cached or persisted locally
 *
 * Props:
 *   summaryState  { status: 'idle'|'loading'|'success'|'error', data, errorMsg }
 *   onGenerate    () => void  — called when operator clicks "Generate AI Summary"
 *   onDismiss     () => void  — called when operator clicks "Dismiss"
 *   dark          boolean
 */
export default function CampaignAiPanel({ summaryState, onGenerate, onDismiss, dark }) {
  const { status, data, errorMsg } = summaryState;

  const panelBorder = dark ? "#4b5563" : "#c7d2fe";
  const panelBg = dark ? "rgba(99,102,241,0.05)" : "rgba(238,242,255,0.6)";
  const warnBg = dark ? "rgba(251,191,36,0.08)" : "rgba(255,251,235,0.9)";
  const warnBorder = dark ? "#92400e" : "#d97706";
  const warnFg = dark ? "#fbbf24" : "#92400e";
  const labelFg = dark ? "#818cf8" : "#6366f1";
  const fg = dark ? "#d1d5db" : "#374151";
  const mutedFg = dark ? "#9ca3af" : "#6b7280";
  const dividerColor = dark ? "#374151" : "#e0e7ff";
  const btnBg = dark ? "rgba(99,102,241,0.18)" : "rgba(99,102,241,0.1)";
  const btnBorder = "#6366f1";
  const btnFg = dark ? "#a5b4fc" : "#4338ca";
  const errorFg = dark ? "#f87171" : "#dc2626";

  // Warning text: prefer server-returned value, fall back to canonical disclaimer.
  const warningText =
    (status === "success" && data?.warning) ||
    "AI-assisted analysis — not an asserted attribution. All factual claims are derived from deterministic campaign data.";

  return (
    <div
      style={{
        marginTop: 16,
        padding: "12px 14px",
        borderRadius: 8,
        border: `1px solid ${panelBorder}`,
        background: panelBg,
      }}
    >
      {/* ── Header row ─────────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 10,
        }}
      >
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            color: labelFg,
          }}
        >
          AI Analysis
        </span>
        {(status === "success" || status === "error") && (
          <button
            onClick={onDismiss}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              fontSize: 12,
              color: mutedFg,
              padding: "2px 6px",
              borderRadius: 4,
            }}
          >
            Dismiss
          </button>
        )}
      </div>

      {/* ── Warning banner — always visible ────────────────────── */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 8,
          padding: "8px 10px",
          borderRadius: 6,
          background: warnBg,
          border: `1px solid ${warnBorder}`,
          color: warnFg,
          fontSize: 12,
          lineHeight: 1.5,
          marginBottom: 12,
        }}
      >
        <span style={{ flexShrink: 0, fontWeight: 700 }}>⚠</span>
        <span>{warningText}</span>
      </div>

      {/* ── Idle: generate button ───────────────────────────────── */}
      {status === "idle" && (
        <button
          onClick={onGenerate}
          style={{
            padding: "6px 14px",
            borderRadius: 6,
            border: `1px solid ${btnBorder}`,
            background: btnBg,
            color: btnFg,
            fontSize: 12,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Generate AI Summary
        </button>
      )}

      {/* ── Loading ─────────────────────────────────────────────── */}
      {status === "loading" && (
        <span style={{ fontSize: 12, color: mutedFg, fontStyle: "italic" }}>
          Generating summary…
        </span>
      )}

      {/* ── Error ───────────────────────────────────────────────── */}
      {status === "error" && (
        <div style={{ fontSize: 12, color: errorFg }}>
          {errorMsg ?? "AI summary unavailable."}
        </div>
      )}

      {/* ── Success ─────────────────────────────────────────────── */}
      {status === "success" && data && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {data.rejected ? (
            /* Output failed safety checks */
            <div style={{ fontSize: 12, color: errorFg }}>
              AI summary unavailable — output did not pass safety checks.
              {data.rejection_reason === "ip_detected" && (
                <span style={{ marginLeft: 4 }}>(Output contained an IP address pattern.)</span>
              )}
            </div>
          ) : (
            /* Valid summary — plain text only, never HTML */
            <>
              <p
                style={{
                  fontSize: 13,
                  color: fg,
                  lineHeight: 1.65,
                  margin: 0,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {data.summary}
              </p>
              {data.truncated && (
                <span style={{ fontSize: 11, color: mutedFg, fontStyle: "italic" }}>
                  Output truncated to 1,000 characters.
                </span>
              )}
            </>
          )}

          {/* ── Metadata footer ───────────────────────────────── */}
          <div
            style={{
              display: "flex",
              gap: 16,
              flexWrap: "wrap",
              fontSize: 11,
              color: mutedFg,
              borderTop: `1px solid ${dividerColor}`,
              paddingTop: 8,
            }}
          >
            {data.generated_at && (
              <span>Generated {new Date(data.generated_at).toLocaleTimeString()}</span>
            )}
            {data.ai_backend && (
              <span>Backend: {data.ai_backend}</span>
            )}
            {data.source_records?.observation_count != null && (
              <span>Observations used: {data.source_records.observation_count}</span>
            )}
            {data.safety_flags?.length > 0 && (
              <span style={{ color: warnFg }}>
                Flags: {data.safety_flags.join(", ")}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
