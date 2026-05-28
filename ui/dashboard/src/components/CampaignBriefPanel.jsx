/**
 * CampaignBriefPanel — operator-triggered multi-campaign AI brief panel.
 *
 * Rendering rules:
 *   - Brief is NEVER auto-generated; operator must click "Generate Brief"
 *   - Warning/disclaimer is always visible, not dismissible
 *   - AI output is plain text — never HTML, never dangerouslySetInnerHTML
 *   - No output is cached or persisted locally
 *   - Polls GET /api/jobs/{job_id} until terminal state
 *   - Stops polling on completed / failed / cancelled
 *   - Handles 429 rate limit at POST time
 *
 * Props:
 *   dark   boolean
 */
import { useEffect, useRef, useState } from "react";
import { getJob, postCampaignBrief } from "../lib/api";

const POLL_INTERVAL_MS = 2000;
const MAX_POLLS = 60; // 2 minutes max

const _WARNING =
  "AI-assisted analysis — not an asserted attribution. All factual claims " +
  "are derived from deterministic campaign data. Operator review required.";

export default function CampaignBriefPanel({ dark }) {
  const [phase, setPhase] = useState("idle"); // idle | submitting | polling | done | error
  const [jobId, setJobId] = useState(null);
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const [maxCampaigns, setMaxCampaigns] = useState(10);
  const [twStart, setTwStart] = useState(""); // date string YYYY-MM-DD
  const [twEnd, setTwEnd] = useState("");

  const pollCountRef = useRef(0);
  const cancelledRef = useRef(false);

  const fg = dark ? "#e5e7eb" : "#111827";
  const mutedFg = dark ? "#9ca3af" : "#6b7280";
  const labelFg = dark ? "#818cf8" : "#6366f1";
  const panelBorder = dark ? "#4b5563" : "#c7d2fe";
  const panelBg = dark ? "rgba(99,102,241,0.05)" : "rgba(238,242,255,0.6)";
  const warnBg = dark ? "rgba(251,191,36,0.08)" : "rgba(255,251,235,0.9)";
  const warnBorder = dark ? "#92400e" : "#d97706";
  const warnFg = dark ? "#fbbf24" : "#92400e";
  const btnBg = dark ? "rgba(99,102,241,0.18)" : "rgba(99,102,241,0.1)";
  const btnBorder = "#6366f1";
  const btnFg = dark ? "#a5b4fc" : "#4338ca";
  const errorFg = dark ? "#f87171" : "#dc2626";
  const inputBg = dark ? "#1f2937" : "#fff";
  const inputFg = dark ? "#e5e7eb" : "#111827";
  const inputBorder = dark ? "#374151" : "#d1d5db";
  const dividerColor = dark ? "#374151" : "#e0e7ff";

  // Polling effect — active only when phase === "polling"
  useEffect(() => {
    if (phase !== "polling" || !jobId) return;

    cancelledRef.current = false;
    pollCountRef.current = 0;

    async function poll() {
      if (cancelledRef.current) return;
      if (pollCountRef.current >= MAX_POLLS) {
        setErrorMsg("Brief timed out. The job may still be running — try again.");
        setPhase("error");
        return;
      }
      pollCountRef.current += 1;
      try {
        const job = await getJob(jobId);
        if (cancelledRef.current) return;
        if (job.status === "completed") {
          setResult(job.result);
          setPhase("done");
        } else if (job.status === "failed" || job.status === "cancelled") {
          setErrorMsg(job.error_message ?? "Brief generation failed.");
          setPhase("error");
        }
        // pending or running → keep polling
      } catch {
        if (!cancelledRef.current) {
          setErrorMsg("Poll request failed. Check your connection.");
          setPhase("error");
        }
      }
    }

    poll(); // immediate first check
    const t = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelledRef.current = true;
      clearInterval(t);
    };
  }, [phase, jobId]);

  async function handleGenerate() {
    setPhase("submitting");
    setResult(null);
    setErrorMsg(null);

    const params = { max_campaigns: maxCampaigns };
    if (twStart && twEnd) {
      // Convert date inputs to ISO 8601 datetime strings (UTC)
      params.time_window_start = `${twStart}T00:00:00+00:00`;
      params.time_window_end = `${twEnd}T23:59:59+00:00`;
    }

    try {
      const { status, data } = await postCampaignBrief(params);
      if (status === 202) {
        setJobId(data.job_id);
        setPhase("polling");
      } else if (status === 429) {
        setErrorMsg("Rate limit reached. Please wait 60 seconds and try again.");
        setPhase("error");
      } else if (status === 422) {
        const detail = data?.detail ?? "Invalid request.";
        setErrorMsg(typeof detail === "string" ? detail : JSON.stringify(detail));
        setPhase("error");
      } else {
        setErrorMsg(`Unexpected response (HTTP ${status}).`);
        setPhase("error");
      }
    } catch {
      setErrorMsg("Network error. Could not reach the API.");
      setPhase("error");
    }
  }

  function handleReset() {
    setPhase("idle");
    setResult(null);
    setErrorMsg(null);
    setJobId(null);
  }

  const isIdle = phase === "idle";
  const isLoading = phase === "submitting" || phase === "polling";
  const isDone = phase === "done";
  const isError = phase === "error";

  return (
    <div
      style={{
        padding: "16px 18px",
        borderRadius: 10,
        border: `1px solid ${panelBorder}`,
        background: panelBg,
      }}
    >
      {/* ── Header ─────────────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 12,
        }}
      >
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            color: labelFg,
          }}
        >
          Multi-Campaign AI Threat Brief
        </span>
        {(isDone || isError) && (
          <button
            onClick={handleReset}
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
            Reset
          </button>
        )}
      </div>

      {/* ── Warning — always visible ────────────────────────────── */}
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
          marginBottom: 14,
        }}
      >
        <span style={{ flexShrink: 0, fontWeight: 700 }}>⚠</span>
        <span>{_WARNING}</span>
      </div>

      {/* ── Idle: controls + generate button ───────────────────── */}
      {isIdle && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {/* max_campaigns */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <label
              htmlFor="brief-max"
              style={{ fontSize: 12, color: mutedFg, minWidth: 110 }}
            >
              Max campaigns
            </label>
            <select
              id="brief-max"
              value={maxCampaigns}
              onChange={(e) => setMaxCampaigns(Number(e.target.value))}
              style={{
                padding: "4px 8px",
                borderRadius: 5,
                border: `1px solid ${inputBorder}`,
                background: inputBg,
                color: inputFg,
                fontSize: 12,
              }}
            >
              {[5, 10, 15, 20, 25].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>

          {/* Time window */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <label
              htmlFor="brief-tw-start"
              style={{ fontSize: 12, color: mutedFg, minWidth: 110 }}
            >
              Time window
            </label>
            <input
              id="brief-tw-start"
              type="date"
              value={twStart}
              onChange={(e) => setTwStart(e.target.value)}
              style={{
                padding: "4px 8px",
                borderRadius: 5,
                border: `1px solid ${inputBorder}`,
                background: inputBg,
                color: inputFg,
                fontSize: 12,
              }}
            />
            <span style={{ fontSize: 12, color: mutedFg }}>to</span>
            <input
              id="brief-tw-end"
              type="date"
              value={twEnd}
              onChange={(e) => setTwEnd(e.target.value)}
              style={{
                padding: "4px 8px",
                borderRadius: 5,
                border: `1px solid ${inputBorder}`,
                background: inputBg,
                color: inputFg,
                fontSize: 12,
              }}
            />
            {(twStart || twEnd) && (
              <button
                onClick={() => { setTwStart(""); setTwEnd(""); }}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  fontSize: 11,
                  color: mutedFg,
                  padding: "2px 4px",
                }}
              >
                Clear
              </button>
            )}
          </div>

          <div>
            <button
              onClick={handleGenerate}
              style={{
                padding: "7px 16px",
                borderRadius: 6,
                border: `1px solid ${btnBorder}`,
                background: btnBg,
                color: btnFg,
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Generate Brief
            </button>
          </div>
        </div>
      )}

      {/* ── Loading / polling ───────────────────────────────────── */}
      {isLoading && (
        <div style={{ fontSize: 12, color: mutedFg, fontStyle: "italic" }}>
          {phase === "submitting" ? "Submitting request…" : "Generating brief — polling for result…"}
        </div>
      )}

      {/* ── Error ───────────────────────────────────────────────── */}
      {isError && (
        <div style={{ fontSize: 12, color: errorFg, marginBottom: 8 }}>
          {errorMsg ?? "Brief generation failed."}
        </div>
      )}

      {/* ── Done ────────────────────────────────────────────────── */}
      {isDone && result && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {result.rejected ? (
            <div style={{ fontSize: 12, color: errorFg }}>
              Brief unavailable — output did not pass safety checks.
              {result.rejection_reason === "ip_detected" && (
                <span style={{ marginLeft: 4 }}>(Output contained an IP address pattern.)</span>
              )}
              {result.rejection_reason === "no_campaigns" && (
                <span style={{ marginLeft: 4 }}>(No campaigns matched the selected criteria.)</span>
              )}
            </div>
          ) : (
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
                {result.summary}
              </p>
              {result.truncated && (
                <span style={{ fontSize: 11, color: mutedFg, fontStyle: "italic" }}>
                  Output truncated to 2,500 characters.
                </span>
              )}
            </>
          )}

          {/* ── Metadata footer ─────────────────────────────────── */}
          <div
            style={{
              display: "flex",
              gap: 14,
              flexWrap: "wrap",
              fontSize: 11,
              color: mutedFg,
              borderTop: `1px solid ${dividerColor}`,
              paddingTop: 8,
            }}
          >
            {result.generated_at && (
              <span>Generated {new Date(result.generated_at).toLocaleTimeString()}</span>
            )}
            {result.campaign_count != null && (
              <span>Campaigns: {result.campaign_count}</span>
            )}
            {result.source_records?.campaign_count != null && (
              <span>Source campaigns: {result.source_records.campaign_count}</span>
            )}
            {result.source_records?.time_window_start && (
              <span>
                Window: {result.source_records.time_window_start.slice(0, 10)}
                {" — "}
                {result.source_records.time_window_end?.slice(0, 10)}
              </span>
            )}
            {result.ai_backend && (
              <span>Backend: {result.ai_backend}</span>
            )}
          </div>
        </div>
      )}

      {/* ── Done but result is null (edge case) ─────────────────── */}
      {isDone && !result && (
        <div style={{ fontSize: 12, color: errorFg }}>
          Brief completed but no result data was returned.
        </div>
      )}
    </div>
  );
}
