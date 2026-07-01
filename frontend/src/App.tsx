import { useEffect, useState } from "react";
import "./App.css";

type HealthResponse = {
  status: string;
  version: string;
};

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/health")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: HealthResponse) => setHealth(data))
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main className="app">
      <header className="app__header">
        <h1>ACH Payment Tracking Agent</h1>
        <p className="app__tagline">
          Where is this customer&apos;s ACH payment right now?
        </p>
      </header>

      <section className="app__panel">
        <h2>Backend status</h2>
        {health && (
          <p>
            <strong>{health.status}</strong> — v{health.version}
          </p>
        )}
        {error && <p className="app__error">Backend unreachable: {error}</p>}
        {!health && !error && <p>Checking backend…</p>}
      </section>

      <section className="app__panel">
        <h2>Planned views</h2>
        <ul>
          <li>Demo simulator</li>
          <li>Batch dashboard</li>
          <li>Customer dashboard</li>
          <li>Payment search / detail</li>
        </ul>
        <p className="app__note">
          UI screens are added in later prompts. This is the bootstrap skeleton.
        </p>
      </section>
    </main>
  );
}
