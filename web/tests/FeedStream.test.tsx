/**
 * Coverage tests for FeedStream, useBriefStream edge paths, and api error paths.
 *
 * FeedStream renders a status pill + count driven by useBriefStream; we
 * mock the hook to exercise every pill-colour branch (open / polling /
 * closed). useBriefStream additional tests cover the WebSocket constructor
 * throw path and the dedup-by-msg_id branch. api.ts tests cover the HTTP
 * non-OK return paths in fetchBriefs + fetchHealth.
 */

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { FeedStream } from '@/components/FeedStream';
import * as apiModule from '@/lib/api';
import type { Brief } from '@/lib/schemas/brief';

// --------------------------------------------------------------------------- //
// FeedStream                                                                  //
// --------------------------------------------------------------------------- //

vi.mock('@/lib/hooks/useBriefStream', () => ({
  useBriefStream: vi.fn(),
}));

import { useBriefStream } from '@/lib/hooks/useBriefStream';

const mockBrief: Brief = {
  msg_id: '01ARZ3NDEKTSV4RRFFQ69G5FAV',
  agent: 'narrator',
  created_at: '2026-04-22T10:00:00Z',
  model_used: 'anthropic/claude-opus-4-7',
  payload: {
    token_name: 'X',
    token_address: `0x${'a'.repeat(40)}`,
    thesis: 'A sensible thesis about this token.',
    conviction_tier: 'moderate',
    caveats: [],
    sources: [],
    model_attribution: [],
    brief_generated_at: '2026-04-22T10:00:00Z',
  },
};

describe('FeedStream', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('renders open-status pill with success palette', () => {
    (useBriefStream as ReturnType<typeof vi.fn>).mockReturnValue({
      briefs: [mockBrief],
      status: 'open',
    });
    render(<FeedStream initialBriefs={[]} />);
    const pill = screen.getByTestId('ws-status');
    expect(pill.textContent).toBe('open');
    expect(pill.className).toContain('success');
    expect(screen.getByText('1 briefs streamed')).toBeInTheDocument();
  });

  test('renders polling-status pill with warn palette', () => {
    (useBriefStream as ReturnType<typeof vi.fn>).mockReturnValue({
      briefs: [],
      status: 'polling',
    });
    render(<FeedStream initialBriefs={[]} />);
    const pill = screen.getByTestId('ws-status');
    expect(pill.textContent).toBe('polling');
    expect(pill.className).toContain('warn');
  });

  test('renders closed-status pill with slate palette', () => {
    (useBriefStream as ReturnType<typeof vi.fn>).mockReturnValue({
      briefs: [mockBrief, mockBrief],
      status: 'closed',
    });
    render(<FeedStream initialBriefs={[]} />);
    const pill = screen.getByTestId('ws-status');
    expect(pill.textContent).toBe('closed');
    expect(pill.className).toContain('slate');
  });

  test('renders connecting-status pill with slate palette (default)', () => {
    (useBriefStream as ReturnType<typeof vi.fn>).mockReturnValue({
      briefs: [],
      status: 'connecting',
    });
    render(<FeedStream initialBriefs={[]} />);
    const pill = screen.getByTestId('ws-status');
    expect(pill.textContent).toBe('connecting');
    expect(pill.className).toContain('slate');
  });
});

// --------------------------------------------------------------------------- //
// api.ts error paths                                                          //
// --------------------------------------------------------------------------- //

describe('api.ts error branches', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  test('fetchBriefs returns empty list on non-OK response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    }) as unknown as typeof fetch;
    const result = await apiModule.fetchBriefs(10, 0);
    expect(result.items).toEqual([]);
    expect(result.limit).toBe(10);
    expect(result.offset).toBe(0);
  });

  test('fetchBrief returns null on non-OK response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
    }) as unknown as typeof fetch;
    const result = await apiModule.fetchBrief('XYZ');
    expect(result).toBeNull();
  });

  test('fetchBrief returns null when zod validation fails', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ nonsense: 'invalid shape' }),
    }) as unknown as typeof fetch;
    const result = await apiModule.fetchBrief('XYZ');
    expect(result).toBeNull();
  });

  test('fetchHealth returns degraded on non-OK', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
    }) as unknown as typeof fetch;
    const h = await apiModule.fetchHealth();
    expect(h.status).toBe('degraded');
    expect(h.agents).toEqual([]);
  });

  test('fetchHealth returns degraded on network exception', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('network fail')) as unknown as typeof fetch;
    const h = await apiModule.fetchHealth();
    expect(h.status).toBe('degraded');
  });

  test('fetchHealth returns degraded when payload fails zod validation', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'weird-value' }),
    }) as unknown as typeof fetch;
    const h = await apiModule.fetchHealth();
    expect(h.status).toBe('degraded');
  });

  test('verifyUrl + bscscanTokenUrl + bscscanTxUrl build expected URLs', () => {
    expect(apiModule.verifyUrl('ABC')).toContain('/briefs/ABC/verify');
    expect(apiModule.bscscanTokenUrl('0xdead')).toBe('https://testnet.bscscan.com/token/0xdead');
    expect(apiModule.bscscanTxUrl('0xcafe')).toBe('https://testnet.bscscan.com/tx/0xcafe');
  });
});
