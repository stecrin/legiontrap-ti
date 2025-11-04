import { useEffect, useState } from "react";

function App() {
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/stats", {
      headers: { "x-api-key": "dev-123" },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setStats(data);
      })
      .catch((err) => setError(err.message));
  }, []);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#0f172a",
        color: "white",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial",
      }}
    >
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 12 }}>
        LegionTrap TI Dashboard
      </h1>

      {error && <p style={{ color: "#fca5a5" }}>⚠️ Error: {error}</p>}

      {stats ? (
        <pre
          style={{
            background: "#111827",
            padding: 16,
            borderRadius: 8,
            width: "80%",
            overflowX: "auto",
            fontSize: 14,
          }}
        >
          {JSON.stringify(stats, null, 2)}
        </pre>
      ) : (
        !error && <p>Loading stats from API...</p>
      )}
    </div>
  );
}

export default App;
