import { ActivityTimelinePanel } from '@/components/ActivityTimelinePanel';
import { BriefCard } from '@/components/BriefCard';
import { FeedStream } from '@/components/FeedStream';
import { ModelUsagePanel } from '@/components/ModelUsagePanel';
import { SwarmHealthPanel } from '@/components/SwarmHealthPanel';
import { fetchBriefs, fetchHealth } from '@/lib/api';

/** Next.js route segment config — always render fresh at request time (no ISR caching). */
export const dynamic = 'force-dynamic';

/**
 * Server-rendered feed page.
 *
 * Fetches briefs and health in parallel at request time, renders the
 * initial feed + sidebar panels, then hands off to the client-side
 * `FeedStream` for live WebSocket updates.
 */
export default async function HomePage() {
  const [briefsResp, health] = await Promise.all([fetchBriefs(50, 0), fetchHealth()]);
  const briefs = briefsResp.items;
  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
      <section aria-label="Live brief feed">
        <div className="mb-4 flex items-baseline justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">Live feed</h1>
          <span className="text-xs text-slate-500">
            {briefs.length} briefs · SSR · auto-updates via WebSocket
          </span>
        </div>
        <FeedStream initialBriefs={briefs} />
        <div className="mt-6 space-y-4">
          {briefs.map((b) => (
            <BriefCard key={b.msg_id} brief={b} />
          ))}
          {briefs.length === 0 && (
            <div className="rounded-lg border border-border bg-surface px-4 py-8 text-center text-slate-500">
              No briefs yet. The swarm is warming up.
            </div>
          )}
        </div>
      </section>
      <aside className="space-y-6">
        <SwarmHealthPanel agents={health.agents} status={health.status} />
        <ModelUsagePanel briefs={briefs} />
        <ActivityTimelinePanel briefs={briefs} />
      </aside>
    </div>
  );
}
