import type { Brief } from '@/lib/schemas/brief';

/**
 * Sidebar panel showing percentage usage across LLM provider/model combinations.
 *
 * Aggregates the `model_attribution` arrays from every brief currently in
 * the feed. Evidence for the demo beat "multi-provider routing visible at
 * a glance".
 */
export function ModelUsagePanel({ briefs }: { briefs: Brief[] }) {
  const counts: Record<string, number> = {};
  for (const b of briefs) {
    for (const m of b.payload.model_attribution) {
      counts[m] = (counts[m] ?? 0) + 1;
    }
  }
  const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
        Model usage
      </h3>
      {entries.length === 0 && <p className="text-xs text-slate-500">No model attributions yet.</p>}
      <ul className="space-y-2">
        {entries.map(([model, n]) => {
          const pct = Math.round((n / total) * 100);
          return (
            <li key={model} className="text-xs" data-testid={`model-${model}`}>
              <div className="mb-0.5 flex justify-between">
                <span className="truncate font-mono">{model}</span>
                <span className="text-slate-500">{pct}%</span>
              </div>
              <div className="h-1 rounded-full bg-border">
                <div
                  className="h-1 rounded-full bg-accent"
                  style={{ width: `${pct}%` }}
                  aria-hidden
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
