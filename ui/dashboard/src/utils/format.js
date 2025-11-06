export function timeAgo(ts) {
  if (!ts) return "–";
  const t = typeof ts === "number" ? ts : Date.parse(ts);
  if (Number.isNaN(t)) return "–";
  const diff = Math.max(0, Date.now() - t);
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function safe(obj, path, fallback = "–") {
  try {
    const v = path.split(".").reduce((acc, k) => (acc == null ? acc : acc[k]), obj);
    return v ?? fallback;
  } catch {
    return fallback;
  }
}
