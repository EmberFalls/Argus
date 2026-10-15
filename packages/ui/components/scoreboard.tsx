export function Scoreboard({ found, total }: { found: number; total: number }) {
  const coverage = total ? Math.round((found / total) * 100) : 0;
  return <section aria-label="Benchmark scoreboard"><strong>{found}/{total}</strong><span> bugs found · {coverage}% coverage</span></section>;
}
