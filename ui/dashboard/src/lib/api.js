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
