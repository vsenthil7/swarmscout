import type { Brief } from '@/lib/schemas/brief';

/**
 * Sidebar panel showing briefs-per-hour for the last 24 hours.
 *
 * Simple column chart with no external charting dependency. Malformed
 * timestamps are silently skipped so a corrupt row never breaks the view.
 */
export function ActivityTimelinePanel({ briefs }: { briefs: Brief[] }) {
  const buckets = new Array(24).fill(0) as number[];
  const now = Date.now();
  for (const b of briefs) {
    const ts = Date.parse(b.created_at);
    if (Number.isNaN(ts)) continue;
    const diffH = Math.floor((now - ts) / 3_600_000);
    if (diffH >= 0 && diffH < 24) {
      buckets[23 - diffH] = (buckets[23 - diffH] ?? 0) + 1;
    }
  }
  const max = Math.max(1, ...buckets);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
        Activity (last 24h)
      </h3>
      <div className="flex h-16 items-end gap-0.5" aria-label="briefs per hour">
        {buckets.map((n, i) => (
          <div
            // eslint-disable-next-line react/no-array-index-key
            key={i}
            className="flex-1 rounded-t bg-accent/70"
            style={{ height: `${(n / max) * 100}%` }}
            title={`${n} briefs`}
            data-testid={`bucket-${i}`}
          />
        ))}
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Total last 24h: {buckets.reduce((a, b) => a + b, 0)}
      </p>
    </div>
  );
}
