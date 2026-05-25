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
