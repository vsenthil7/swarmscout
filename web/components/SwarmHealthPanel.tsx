import type { AgentHeartbeat, Brief } from '@/lib/schemas/brief';
import clsx from 'clsx';

/**
 * Sidebar panel showing per-agent heartbeat status plus a top-level status dot.
 *
 * Renders an empty state when the heartbeat table is empty — the dashboard
 * should not look broken just because the agents haven't written their
 * first heartbeat yet.
 */
export function SwarmHealthPanel({
  agents,
  status,
}: {
  agents: AgentHeartbeat[];
  status: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Swarm health
        </h3>
        <span
          className={clsx('h-2 w-2 rounded-full', status === 'ok' ? 'bg-success' : 'bg-warn')}
          aria-label={`status: ${status}`}
        />
      </div>
      <ul className="space-y-1.5">
        {agents.length === 0 && <li className="text-xs text-slate-500">No heartbeats yet.</li>}
        {agents.map((a) => (
          <li
            key={a.agent}
            className="flex items-center justify-between text-xs"
            data-testid={`agent-${a.agent}`}
          >
            <span className="capitalize">{a.agent}</span>
            <span className="flex items-center gap-2">
              <span className="text-slate-500">{a.events_last_min}/min</span>
              <span
                className={clsx(
                  'h-1.5 w-1.5 rounded-full',
                  a.status === 'online' ? 'bg-success' : 'bg-danger',
                )}
              />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
