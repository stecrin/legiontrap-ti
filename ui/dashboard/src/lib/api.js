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

export async function getJob(jobId) {
  const r = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, {
    headers: { 'x-api-key': 'dev-123' },
  });
  if (!r.ok) throw new Error(`jobs/${jobId} ${r.status}`);
  return r.json();
}
