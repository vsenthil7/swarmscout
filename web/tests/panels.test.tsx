/**
 * Unit tests for the three sidebar panels, zod schemas, and the api.ts helpers.
 *
 * Mocks `globalThis.fetch` per test for API-client assertions. The `brief()`
 * factory builds a minimally-valid Brief; callers override fields via the
 * partial argument.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SwarmHealthPanel } from '@/components/SwarmHealthPanel';
import { ModelUsagePanel } from '@/components/ModelUsagePanel';
import { ActivityTimelinePanel } from '@/components/ActivityTimelinePanel';
import { briefSchema, healthSchema, agentHeartbeatSchema } from '@/lib/schemas/brief';
import type { Brief } from '@/lib/schemas/brief';
import { fetchBriefs, fetchBrief, fetchHealth, bscscanTokenUrl, bscscanTxUrl, verifyUrl } from '@/lib/api';

const brief = (partial: Partial<Brief> = {}): Brief => ({
  msg_id: partial.msg_id ?? '01ARZ3NDEKTSV4RRFFQ69G5FAV',
  payload: {
    token_name: 'X',
    token_address: '0x0000000000000000000000000000000000000001',
    thesis: 't',
    conviction_tier: 'degen',
    caveats: [],
    sources: [],
    model_attribution: ['openai/gpt-4o'],
    brief_generated_at: '2026-04-22T06:50:00Z',
    confidence_tier: 'ok',
  },
  payload_hash: 'a'.repeat(64),
  upstream_ids: [],
  model_used: 'openai/gpt-4o',
  created_at: new Date().toISOString(),
  on_chain_tx: null,
  on_chain_block: null,
  ...partial,
});

describe('SwarmHealthPanel', () => {
  it('renders agents with status dots', () => {
    render(
      <SwarmHealthPanel
        status="ok"
        agents={[
          {
            agent: 'hunter',
            status: 'online',
            events_last_min: 3,
            current_model: null,
            llm_error_rate: 0,
            last_seen: '',
          },
        ]}
      />,
    );
    expect(screen.getByTestId('agent-hunter')).toBeInTheDocument();
  });

  it('shows empty-state when no heartbeats', () => {
    render(<SwarmHealthPanel status="degraded" agents={[]} />);
    expect(screen.getByText(/No heartbeats yet/)).toBeInTheDocument();
  });
});

describe('ModelUsagePanel', () => {
  it('aggregates counts across briefs', () => {
    render(<ModelUsagePanel briefs={[brief(), brief({ msg_id: 'x' })]} />);
    expect(screen.getByTestId('model-openai/gpt-4o')).toBeInTheDocument();
  });

  it('shows empty-state with no briefs', () => {
    render(<ModelUsagePanel briefs={[]} />);
    expect(screen.getByText(/No model attributions yet/)).toBeInTheDocument();
  });
});

describe('ActivityTimelinePanel', () => {
  it('renders 24 buckets', () => {
    render(<ActivityTimelinePanel briefs={[brief()]} />);
    for (let i = 0; i < 24; i += 1) {
      expect(screen.getByTestId(`bucket-${i}`)).toBeInTheDocument();
    }
  });

  it('tolerates malformed timestamps', () => {
    render(<ActivityTimelinePanel briefs={[brief({ created_at: 'not-a-date' })]} />);
    expect(screen.getByText(/Total last 24h/)).toBeInTheDocument();
  });
});

describe('schemas', () => {
  it('accepts a valid brief', () => {
    expect(briefSchema.safeParse(brief()).success).toBe(true);
  });

  it('rejects a brief missing fields', () => {
    expect(briefSchema.safeParse({}).success).toBe(false);
  });

  it('accepts a valid health payload', () => {
    expect(healthSchema.safeParse({ status: 'ok', agents: [] }).success).toBe(true);
  });

  it('accepts heartbeat with defaults', () => {
    expect(
      agentHeartbeatSchema.safeParse({
        agent: 'x',
        status: 'online',
        current_model: null,
        last_seen: '',
      }).success,
    ).toBe(true);
  });
});

describe('api helpers', () => {
  it('formats BscScan URLs', () => {
    expect(bscscanTokenUrl('0xabc')).toBe('https://testnet.bscscan.com/token/0xabc');
    expect(bscscanTxUrl('0xdef')).toBe('https://testnet.bscscan.com/tx/0xdef');
  });

  it('builds a verify URL', () => {
    expect(verifyUrl('abc')).toContain('/briefs/abc/verify');
  });

  it('returns empty on bad response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false }) as unknown as typeof fetch;
    const resp = await fetchBriefs();
    expect(resp.items).toEqual([]);
  });

  it('returns null when brief fetch fails', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: false }) as unknown as typeof fetch;
    expect(await fetchBrief('x')).toBeNull();
  });

  it('parses a successful brief fetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => brief(),
    }) as unknown as typeof fetch;
    const b = await fetchBrief('01ARZ3NDEKTSV4RRFFQ69G5FAV');
    expect(b?.payload.token_name).toBe('X');
  });

  it('degrades to empty health on thrown fetch', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('offline')) as unknown as typeof fetch;
    const h = await fetchHealth();
    expect(h.status).toBe('degraded');
  });

  it('degrades health on malformed response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ not: 'valid' }),
    }) as unknown as typeof fetch;
    const h = await fetchHealth();
    expect(h.status).toBe('degraded');
  });

  it('returns list of parsed briefs on success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [brief(), { garbage: true }], limit: 50, offset: 0 }),
    }) as unknown as typeof fetch;
    const r = await fetchBriefs();
    expect(r.items).toHaveLength(1);
  });
});
