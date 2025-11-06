import { useEffect, useRef, useState } from 'react';
import { getStats, getPfConf } from './lib/api';
import RecentEvents from "./components/RecentEvents";

// keep <body> background in sync with dashboard theme
function useBodyBgSync(color) {
  useEffect(() => {
    document.body.style.background = color;
  }, [color]);
}

function Dot({ ok }) {
  const color = ok ? '#22c55e' : '#ef4444';
  const label = ok ? 'Connected' : 'Disconnected';
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{
        width: 10, height: 10, borderRadius: '50%',
        background: color, display: 'inline-block', boxShadow: `0 0 12px ${color}88`
      }} />
      <span style={{ opacity: 0.8 }}>{label}</span>
    </span>
  );
}

// Lightweight animated number counter (tween ~300ms)
function Counter({ value, style }) {
  const [display, setDisplay] = useState(Number(value || 0));
  const targetRef = useRef(Number(value || 0));

  useEffect(() => {
    const from = targetRef.current;
    const to = Number(value || 0);
    targetRef.current = to;

    if (from === to) {
      setDisplay(to);
      return;
    }
    const duration = 300;
    const start = performance.now();

    let raf = requestAnimationFrame(function step(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      const v = Math.round(from + (to - from) * eased);
      setDisplay(v);
      if (t < 1) raf = requestAnimationFrame(step);
    });

    return () => cancelAnimationFrame(raf);
  }, [value]);

  return <span style={style}>{display}</span>;
}

export default function App() {
  const [stats, setStats] = useState(null);
  const [pf, setPf] = useState('');
  const [dark, setDark] = useState(true);
  const [err, setErr] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);
  const loadingRef = useRef(false);

  async function load() {
    if (loadingRef.current) return;
    loadingRef.current = true;
    try {
      // prevent proxy/Vite caching by adding a query param
      const ts = Date.now();
      const [s, p] = await Promise.all([
        getStats(ts),
        getPfConf(ts),
      ]);
      setStats(s);
      setPf(p);
      setErr('');
      setLastUpdated(new Date());
    } catch (e) {
      console.error(e);
      setErr('Backend unreachable…');
    } finally {
      loadingRef.current = false;
    }
  }

  // Auto-refresh
  useEffect(() => {
    load();                      // initial
    const t = setInterval(load, 10000); // every 10s
    return () => clearInterval(t);
  }, []);

  // Log theme changes for debugging
  useEffect(() => {
    console.log("🌓 DARK MODE ACTIVE:", dark);
  }, [dark]);

  const bg = dark ? '#0f1115' : '#f7f7f7';
  const fg = dark ? '#f4f6fa' : '#111';
  const cardBg = dark ? '#171a21' : '#fff';
  const border = dark ? '#2a2f3a' : '#e5e7eb';

  // sync body background
  useBodyBgSync(bg);

  const total = stats?.counts?.total ?? 0;
  const uniq = stats?.unique_ips ?? 0;
  const last24 = stats?.counts?.last_24h ?? 0;
  const connected = !err;

  return (
    <div
      style={{
        fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, Inter, Arial',
        background: bg,
        color: fg,
        minHeight: '100vh',
        width: '100%',
        overflowX: 'hidden',
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '1600px',
          margin: '0 auto',
          padding: '24px clamp(16px, 3vw, 40px)',
        }}
      >
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <h1 style={{ fontSize: 34, fontWeight: 800, letterSpacing: 0.3, margin: 0 }}>
              LegionTrap TI Dashboard
            </h1>
            <Dot ok={connected} />
          </div>
          <button
            onClick={() => setDark(!dark)}
            style={{
              padding: '8px 14px',
              borderRadius: 10,
              border: `1px solid ${border}`,
              cursor: 'pointer',
              background: dark ? '#fff' : '#222',
              color: dark ? '#000' : '#fff',
              fontWeight: 600,
            }}
            aria-label="Toggle theme"
          >
            {dark ? '☀️ Light Mode' : '🌙 Dark Mode'}
          </button>
        </header>

        <p style={{ opacity: 0.75, marginTop: 6 }}>
          Live backend via Vite proxy → FastAPI
          {lastUpdated && (
            <span style={{ marginLeft: 10, opacity: 0.7 }}>
              · Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          {err && <span style={{ color: '#f66', marginLeft: 10 }}>({err})</span>}
        </p>

        {/* KPI cards */}
        <section style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, minmax(180px, 1fr))',
          gap: 16,
          marginTop: 24
        }}>
          <Card title="Total events" value={<Counter value={total} />} cardBg={cardBg} border={border} />
          <Card title="Unique IPs" value={<Counter value={uniq} />} cardBg={cardBg} border={border} />
          <Card title="Last 24 h" value={<Counter value={last24} />} cardBg={cardBg} border={border} />
        </section>

        {/* PF preview */}
        <section style={{ marginTop: 28 }}>
          <h3 style={{ marginBottom: 10, fontSize: 18, opacity: 0.9 }}>PF Block Table (preview)</h3>
          <pre style={{
            background: cardBg,
            color: fg,
            padding: 16,
            borderRadius: 12,
            border: `1px solid ${border}`,
            overflowX: 'auto',
            whiteSpace: 'pre-wrap',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
            fontSize: 13,
            lineHeight: 1.4,
          }}>
{pf || 'Loading…'}
          </pre>
        </section>

        {/* Recent Events Table */}
        <div style={{ marginTop: 28 }}>
          <RecentEvents dark={dark} />
        </div>
      </div>
    </div>
  );
}

function Card({ title, value, cardBg, border }) {
  return (
    <div style={{
      padding: 16,
      borderRadius: 12,
      boxShadow: '0 6px 20px rgba(0,0,0,0.08)',
      background: cardBg,
      border: `1px solid ${border}`,
      textAlign: 'center'
    }}>
      <div style={{ fontSize: 13, opacity: 0.7 }}>{title}</div>
      <div style={{ fontSize: 28, fontWeight: 700, marginTop: 6 }}>{value}</div>
    </div>
  );
}
