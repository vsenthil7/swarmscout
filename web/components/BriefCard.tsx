import clsx from 'clsx';
import { ExternalLink, ShieldCheck } from 'lucide-react';
import type { Brief } from '@/lib/schemas/brief';
import { bscscanTokenUrl, verifyUrl } from '@/lib/api';

const TIER_COLORS: Record<Brief['payload']['conviction_tier'], string> = {
  high: 'bg-success/15 text-success border-success/30',
  moderate: 'bg-accent/15 text-accent border-accent/30',
  speculative: 'bg-warn/15 text-warn border-warn/30',
  degen: 'bg-danger/15 text-danger border-danger/30',
};

/**
 * Visual card for one AlphaBrief.
 *
 * Shows token name, address, conviction tier as a coloured pill, thesis
 * prose, up to 5 caveats, and BscScan + Verify links. The `data-testid`
 * attributes are used by Playwright; don't remove them without updating
 * the E2E specs.
 */
export function BriefCard({ brief }: { brief: Brief }) {
  const p = brief.payload;
  const tier = p.conviction_tier;

  return (
    <article
      className="rounded-lg border border-border bg-surface p-4 shadow-sm transition-colors hover:border-slate-600"
      data-testid={`brief-${brief.msg_id}`}
    >
      <header className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{p.token_name}</h2>
          <p className="mt-1 font-mono text-xs text-slate-500">{p.token_address}</p>
        </div>
        <span
          className={clsx(
            'rounded-full border px-2.5 py-0.5 text-xs font-medium uppercase tracking-wider',
            TIER_COLORS[tier],
          )}
        >
          {tier}
        </span>
      </header>
      <p className="whitespace-pre-line text-sm leading-relaxed text-slate-300">{p.thesis}</p>
      {p.caveats.length > 0 && (
        <div className="mt-3 rounded-md border border-border bg-bg/50 p-3 text-xs text-slate-400">
          <p className="mb-1 font-medium text-slate-300">Caveats</p>
          <ul className="list-disc space-y-0.5 pl-4">
            {p.caveats.slice(0, 5).map((c, i) => (
              // The caveat list is stable for a given brief — the index key is safe here.
              // eslint-disable-next-line react/no-array-index-key
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      <footer className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
        <a
          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 hover:text-slate-200"
          href={bscscanTokenUrl(p.token_address)}
          target="_blank"
          rel="noreferrer"
          data-testid={`bscscan-${brief.msg_id}`}
        >
          <ExternalLink className="h-3 w-3" /> BscScan
        </a>
        <a
          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 hover:text-slate-200"
          href={verifyUrl(brief.msg_id)}
          target="_blank"
          rel="noreferrer"
          data-testid={`verify-${brief.msg_id}`}
        >
          <ShieldCheck className="h-3 w-3" /> Verify
        </a>
        <span className="ml-auto font-mono">{brief.msg_id}</span>
        {p.model_attribution.length > 0 && (
          <span className="text-slate-600">models: {p.model_attribution.join(', ')}</span>
        )}
      </footer>
    </article>
  );
}
