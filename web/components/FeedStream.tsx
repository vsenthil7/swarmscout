'use client';

import { useBriefStream } from '@/lib/hooks/useBriefStream';
import type { Brief } from '@/lib/schemas/brief';
import clsx from 'clsx';
import { BriefCard } from './BriefCard';

/**
 * Client-side WebSocket status strip above the feed.
 *
 * Shows a pill with connection status (connecting / open / closed /
 * polling) and the count of briefs currently held in the stream buffer.
 * Delegates the actual wire work to `useBriefStream`.
 */
export function FeedStream({ initialBriefs }: { initialBriefs: Brief[] }) {
  const { briefs, status } = useBriefStream(initialBriefs);
  const pill =
    status === 'open'
      ? 'bg-success/20 text-success'
      : status === 'polling'
        ? 'bg-warn/20 text-warn'
        : 'bg-slate-700/40 text-slate-400';
  return (
    <div className="mb-2 flex items-center gap-2 text-xs">
      <span className={clsx('rounded-full px-2 py-0.5', pill)} data-testid="ws-status">
        {status}
      </span>
      <span className="text-slate-500">{briefs.length} briefs streamed</span>
    </div>
  );
}
