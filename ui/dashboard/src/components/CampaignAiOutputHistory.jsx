/**
 * CampaignAiOutputHistory — read-only history of persisted AI output records
 * for a single campaign, with an operator-triggered regenerate flow.
 *
 * Rules:
 *   - No auto-generation on mount; fetch is read-only history retrieval
 *   - "Historical AI output" warning is always visible, not dismissible
 *   - Output content is plain text only — never HTML, never dangerouslySetInnerHTML
 *   - No AI output is fed back into any prompt (enforced by backend)
 *   - No editing or deleting of stored outputs
 *   - No localStorage
 *
 * Props:
 *   campaignId  string
 *   dark        boolean
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getCampaignAiOutputs, getJob, postCampaignSummary } from '../lib/api';

const POLL_INTERVAL_MS = 2000;
const MAX_POLLS = 60;

function OutputCard({ output, dark, fg, mutedFg, border, cardBg, errorFg }) {
  const badgeRejFg = dark ? '#f87171' : '#dc2626';
  const badgeTruncFg = dark ? '#fbbf24' : '#92400e';
  const scoreFg = dark ? '#a78bfa' : '#7c3aed';
  const src = output.source_records;

  return (
    <div style={{
      padding: '10px 12px',
      borderRadius: 6,
      border: `1px solid ${border}`,
      background: cardBg,
    }}>
      <div style={{
        display: 'flex',
        gap: 12,
        flexWrap: 'wrap',
        alignItems: 'center',
        fontSize: 11,
        color: mutedFg,
        marginBottom: (output.content && !output.rejected) || (output.rejected && output.rejection_reason) ? 8 : 0,
      }}>
        <span>{new Date(output.generated_at).toLocaleString()}</span>
        <span>{output.backend}/{output.model_name}</span>
        {output.data_quality_score != null && (
          <span style={{ color: scoreFg }}>
            quality {Math.round(output.data_quality_score * 100)}%
          </span>
        )}
        {output.rejected && (
          <span style={{
            padding: '1px 5px',
            borderRadius: 4,
            background: `${badgeRejFg}22`,
            color: badgeRejFg,
            fontWeight: 700,
            textTransform: 'uppercase',
            fontSize: 10,
          }}>rejected</span>
        )}
        {!output.rejected && output.truncated && (
          <span style={{
            padding: '1px 5px',
            borderRadius: 4,
            background: `${badgeTruncFg}22`,
            color: badgeTruncFg,
            fontWeight: 600,
            textTransform: 'uppercase',
            fontSize: 10,
          }}>truncated</span>
        )}
        {src?.observation_count != null && (
          <span>{src.observation_count} obs</span>
        )}
        {src?.member_ip_count != null && (
          <span>{src.member_ip_count} IPs</span>
        )}
      </div>

      {output.rejected && output.rejection_reason && (
        <div style={{ fontSize: 11, color: errorFg, marginBottom: 0 }}>
          Rejected: {output.rejection_reason}
        </div>
      )}

      {output.content && !output.rejected && (
        <p style={{
          fontSize: 12,
          color: fg,
          lineHeight: 1.6,
          margin: 0,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}>
          {output.content}
        </p>
      )}
    </div>
  );
}

export default function CampaignAiOutputHistory({ campaignId, dark }) {
  const [outputs, setOutputs] = useState([]);
  const [loadState, setLoadState] = useState('loading');
  const [loadError, setLoadError] = useState(null);
  const [regenPhase, setRegenPhase] = useState('idle');
  const [regenError, setRegenError] = useState(null);
  const [pollCount, setPollCount] = useState(0);

  const jobIdRef = useRef(null);
  const pollCountRef = useRef(0);
  const pollTimerRef = useRef(null);
  const pollJobRef = useRef(null);

  const panelBorder = dark ? '#374151' : '#d1d5db';
  const panelBg = dark ? 'rgba(16,185,129,0.04)' : 'rgba(236,253,245,0.6)';
  const labelFg = dark ? '#34d399' : '#059669';
  const fg = dark ? '#d1d5db' : '#374151';
  const mutedFg = dark ? '#9ca3af' : '#6b7280';
  const border = dark ? '#374151' : '#e5e7eb';
  const warnBg = dark ? 'rgba(251,191,36,0.08)' : 'rgba(255,251,235,0.9)';
  const warnBorder = dark ? '#92400e' : '#d97706';
  const warnFg = dark ? '#fbbf24' : '#92400e';
  const errorFg = dark ? '#f87171' : '#dc2626';
  const btnBg = dark ? 'rgba(52,211,153,0.12)' : 'rgba(16,185,129,0.08)';
  const btnBorder = '#10b981';
  const btnFg = dark ? '#34d399' : '#065f46';
  const cardBg = dark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.02)';

  const fetchHistory = useCallback(async () => {
    try {
      const data = await getCampaignAiOutputs(campaignId);
      setOutputs(data.outputs ?? []);
      setLoadState('done');
    } catch {
      setLoadError('Failed to load AI output history.');
      setLoadState('error');
    }
  }, [campaignId]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  function stopPolling() {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }

  // Reassigned each render so interval callback always has fresh closure
  pollJobRef.current = async function pollJob() {
    if (pollCountRef.current >= MAX_POLLS) {
      stopPolling();
      setRegenPhase('error');
      setRegenError('Timed out waiting for AI summary.');
      return;
    }
    pollCountRef.current += 1;
    setPollCount(pollCountRef.current);
    try {
      const job = await getJob(jobIdRef.current);
      if (job.status === 'completed') {
        stopPolling();
        await fetchHistory();
        setRegenPhase('done');
      } else if (job.status === 'failed') {
        stopPolling();
        setRegenPhase('error');
        setRegenError(job.error_message ?? 'AI summary generation failed.');
      }
    } catch {
      stopPolling();
      setRegenPhase('error');
      setRegenError('Failed to poll job status.');
    }
  };

  async function handleRegenerate() {
    if (regenPhase === 'submitting' || regenPhase === 'polling') return;
    setRegenPhase('submitting');
    setRegenError(null);
    pollCountRef.current = 0;
    setPollCount(0);
    try {
      const { status, data } = await postCampaignSummary(campaignId);
      const jobId = data?.job_id;
      if (jobId && (status === 202 || status === 200)) {
        jobIdRef.current = jobId;
        setRegenPhase('polling');
        pollTimerRef.current = setInterval(() => pollJobRef.current(), POLL_INTERVAL_MS);
      } else {
        const msg = data?.detail ?? `Unexpected response (${status}).`;
        setRegenPhase('error');
        setRegenError(msg);
      }
    } catch {
      setRegenPhase('error');
      setRegenError('Network error. Could not submit regenerate request.');
    }
  }

  useEffect(() => () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const isRegenerating = regenPhase === 'submitting' || regenPhase === 'polling';

  return (
    <div style={{
      marginTop: 16,
      padding: '12px 14px',
      borderRadius: 8,
      border: `1px solid ${panelBorder}`,
      background: panelBg,
    }}>
      {/* Header row */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 10,
      }}>
        <span style={{
          fontSize: 11,
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: labelFg,
        }}>
          AI Output History
        </span>
        <button
          onClick={handleRegenerate}
          disabled={isRegenerating}
          style={{
            padding: '4px 10px',
            borderRadius: 6,
            border: `1px solid ${isRegenerating ? (dark ? '#374151' : '#d1d5db') : btnBorder}`,
            background: isRegenerating ? 'transparent' : btnBg,
            color: isRegenerating ? mutedFg : btnFg,
            fontSize: 11,
            fontWeight: 600,
            cursor: isRegenerating ? 'default' : 'pointer',
          }}
        >
          {isRegenerating ? 'Generating…' : 'Regenerate Summary'}
        </button>
      </div>

      {/* Historical AI output warning — always visible, not dismissible */}
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
        padding: '8px 10px',
        borderRadius: 6,
        background: warnBg,
        border: `1px solid ${warnBorder}`,
        color: warnFg,
        fontSize: 12,
        lineHeight: 1.5,
        marginBottom: 12,
      }}>
        <span style={{ flexShrink: 0, fontWeight: 700 }}>⚠</span>
        <span>
          Historical AI output — stored records from past AI analysis runs. Not an asserted attribution.
          All factual claims are derived from deterministic campaign data at the time of generation.
        </span>
      </div>

      {/* Regenerate status feedback */}
      {regenPhase === 'submitting' && (
        <div style={{ fontSize: 12, color: mutedFg, fontStyle: 'italic', marginBottom: 10 }}>
          Submitting regenerate request…
        </div>
      )}
      {regenPhase === 'polling' && (
        <div style={{ fontSize: 12, color: mutedFg, fontStyle: 'italic', marginBottom: 10 }}>
          Generating AI summary… ({pollCount}/{MAX_POLLS})
        </div>
      )}
      {regenPhase === 'done' && (
        <div style={{ fontSize: 12, color: labelFg, marginBottom: 10 }}>
          New summary added to history.
        </div>
      )}
      {regenPhase === 'error' && regenError && (
        <div style={{ fontSize: 12, color: errorFg, marginBottom: 10 }}>
          {regenError}
        </div>
      )}

      {/* History list */}
      {loadState === 'loading' && (
        <div style={{ fontSize: 12, color: mutedFg, fontStyle: 'italic' }}>Loading history…</div>
      )}
      {loadState === 'error' && (
        <div style={{ fontSize: 12, color: errorFg }}>{loadError}</div>
      )}
      {loadState === 'done' && outputs.length === 0 && (
        <div style={{ fontSize: 12, color: mutedFg, fontStyle: 'italic' }}>
          No AI outputs recorded for this campaign.
        </div>
      )}
      {loadState === 'done' && outputs.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {outputs.map((output) => (
            <OutputCard
              key={output.id}
              output={output}
              dark={dark}
              fg={fg}
              mutedFg={mutedFg}
              border={border}
              cardBg={cardBg}
              errorFg={errorFg}
            />
          ))}
        </div>
      )}
    </div>
  );
}
