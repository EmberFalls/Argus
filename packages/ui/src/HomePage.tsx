import { useState } from "react";
import type { CreateRunRequest, RunMetrics, RunSummary } from "@/lib/generated/contracts";
import { argusApiUrl } from "@/lib/api";

export default function HomePage() {
  const [url, setUrl] = useState("");
  const [spec, setSpec] = useState("");
  const [status, setStatus] = useState("Runs are executed by the local Argus API.");
  const [metrics, setMetrics] = useState<RunMetrics | null>(null);
  async function startRun(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setStatus("Starting browser run…"); setMetrics(null);
    try {
      const request: CreateRunRequest = { url, spec };
      const response = await fetch(`${argusApiUrl}/runs`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Run failed");
      const result = data as RunSummary;
      setMetrics(result.metrics ?? null); setStatus("Run complete. Evidence was saved by the agent.");
    } catch (error) { setStatus(error instanceof Error ? error.message : "Unable to reach Argus API."); }
  }
  return <main className="shell">
    <header className="topbar"><a className="brand" href="/">ARGUS<span>◆</span></a><span className="eyebrow">AUTONOMOUS QA ENGINEER</span></header>
    <section><p className="eyebrow">Evidence over assertion</p><h1>Ship with confidence.<br/>See what your users see.</h1>
      <p className="lede">Argus explores web applications, runs repeatable browser journeys, and captures the evidence developers need to reproduce failures.</p></section>
    <section className="grid">
      <div className="panel"><h2>Start a QA run</h2><form className="form" onSubmit={startRun}>
        <label>Application URL<input required type="url" placeholder="http://localhost:3100" value={url} onChange={e => setUrl(e.target.value)}/></label>
        <label>What should the app do?<textarea required placeholder="A user can sign in and publish an article…" value={spec} onChange={e => setSpec(e.target.value)}/></label>
        <button className="button" type="submit">Explore application ↗</button><p className="status" aria-live="polite">{status}</p>
      </form></div>
      <div className="panel"><h2>Run scoreboard</h2><div className="stats">
        <div className="stat"><strong>{metrics?.journeys ?? "—"}</strong><small>Journeys</small></div>
        <div className="stat"><strong>{metrics?.passed ?? "—"}</strong><small>Passed</small></div>
        <div className="stat"><strong>{metrics?.failed ?? "—"}</strong><small>Failed</small></div>
        <div className="stat"><strong>—</strong><small>Verified bugs</small></div>
      </div><ul className="list"><li>Semantic browser inventory</li><li>Console and network evidence</li><li>Reproducible journey artifacts</li></ul></div>
    </section>
    <footer className="eyebrow" style={{ marginTop: 28 }}>LOCAL DEVELOPMENT BUILD · MODEL REASONING IS NOT CONFIGURED</footer>
  </main>;
}
