export async function getStats(ts = Date.now()) {
  const r = await fetch(`/api/stats?ts=${ts}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`stats ${r.status}`);
  return r.json();
}

export async function getPfConf(ts = Date.now()) {
  const r = await fetch(`/api/iocs/pf.conf?ts=${ts}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`pf.conf ${r.status}`);
  return r.text();
}

export async function getIntelligenceIPs(ts = Date.now()) {
  const r = await fetch(`/api/intelligence/ips?limit=25&ts=${ts}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`intelligence/ips ${r.status}`);
  return r.json();
}

export async function getIntelligenceIP(ip) {
  const r = await fetch(`/api/intelligence/ips/${encodeURIComponent(ip)}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`intelligence/ips/${ip} ${r.status}`);
  return r.json();
}

export async function getTopCountries(ts = Date.now()) {
  const r = await fetch(`/api/intelligence/top-countries?ts=${ts}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`top-countries ${r.status}`);
  return r.json();
}

export async function getTopASNs(ts = Date.now()) {
  const r = await fetch(`/api/intelligence/top-asns?ts=${ts}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`top-asns ${r.status}`);
  return r.json();
}

export async function getCampaigns(ts = Date.now()) {
  const r = await fetch(`/api/campaigns?ts=${ts}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`campaigns ${r.status}`);
  return r.json();
}

export async function getCampaignDetail(campaignId) {
  const r = await fetch(`/api/campaigns/${encodeURIComponent(campaignId)}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`campaigns/${campaignId} ${r.status}`);
  return r.json();
}

export async function postCampaignSummary(campaignId) {
  const r = await fetch(`/api/campaigns/${encodeURIComponent(campaignId)}/summary`, {
    method: 'POST',
    headers: { 'x-api-key': 'dev-123' },
  });
  const body = await r.json();
  return { status: r.status, data: body };
}

export async function postCampaignBrief({
  max_campaigns = 10,
  time_window_start = null,
  time_window_end = null,
} = {}) {
  const body = { max_campaigns };
  if (time_window_start && time_window_end) {
    body.time_window_start = time_window_start;
    body.time_window_end = time_window_end;
  }
  const r = await fetch('/api/campaigns/brief', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-api-key': 'dev-123' },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  return { status: r.status, data };
}

export async function getSparseCampaigns({ limit = 200 } = {}) {
  const r = await fetch(`/api/campaigns/sparse?limit=${limit}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`campaigns/sparse ${r.status}`);
  return r.json();
}

export async function getCampaignDensity(campaignId) {
  const r = await fetch(`/api/campaigns/${encodeURIComponent(campaignId)}/density`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`campaigns/${campaignId}/density ${r.status}`);
  return r.json();
}

export async function getCampaignAiOutputs(campaignId, { limit = 20 } = {}) {
  const r = await fetch(`/api/campaigns/${encodeURIComponent(campaignId)}/ai-outputs?limit=${limit}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`ai-outputs ${r.status}`);
  return r.json();
}

export async function getAiOutput(outputId) {
  const r = await fetch(`/api/ai/outputs/${encodeURIComponent(outputId)}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`ai/outputs/${outputId} ${r.status}`);
  return r.json();
}

export async function getJob(jobId) {
  const r = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {
    headers: { 'x-api-key': 'dev-123' },
  });
  if (!r.ok) throw new Error(`jobs/${jobId} ${r.status}`);
  return r.json();
}

export async function getActors({ status, limit } = {}) {
  const p = new URLSearchParams();
  if (status != null) p.set('status', status);
  if (limit != null) p.set('limit', limit);
  const qs = p.toString();
  const r = await fetch(`/api/actors${qs ? '?' + qs : ''}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`actors ${r.status}`);
  return r.json();
}

export async function getActor(actorId) {
  const r = await fetch(`/api/actors/${encodeURIComponent(actorId)}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`actors/${actorId} ${r.status}`);
  return r.json();
}

export async function getActorStability(actorId) {
  const r = await fetch(`/api/actors/${encodeURIComponent(actorId)}/stability`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`actors/${actorId}/stability ${r.status}`);
  return r.json();
}

export async function getActorSuggestions({ minScore, limit } = {}) {
  const p = new URLSearchParams();
  if (minScore != null) p.set('min_score', minScore);
  if (limit != null) p.set('limit', limit);
  const qs = p.toString();
  const r = await fetch(`/api/actors/suggestions${qs ? '?' + qs : ''}`, { headers: { 'x-api-key': 'dev-123' } });
  if (!r.ok) throw new Error(`actors/suggestions ${r.status}`);
  return r.json();
}
