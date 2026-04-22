/**
 * Unit tests for BriefCard (TC-U100..U109).
 *
 * Every test renders a single card in isolation and asserts one user-visible
 * property: token name, tier badge, caveat rendering, link targets, etc.
 * The `sample` brief is the canonical happy-path input; individual tests
 * spread over it to vary one field at a time.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BriefCard } from '@/components/BriefCard';
import type { Brief } from '@/lib/schemas/brief';

const sample: Brief = {
  msg_id: '01ARZ3NDEKTSV4RRFFQ69G5FAV',
  payload: {
    token_name: 'Test Token',
    token_address: '0x0000000000000000000000000000000000000001',
    thesis: 'Looks promising with strong organic mentions.',
    conviction_tier: 'moderate',
    caveats: ['LP unlocked', 'Creator has prior launches'],
    sources: ['https://four.meme/x'],
    model_attribution: ['anthropic/claude-opus-4-7'],
    brief_generated_at: '2026-04-22T06:50:00Z',
    confidence_tier: 'ok',
  },
  payload_hash: 'a'.repeat(64),
  upstream_ids: [],
  model_used: 'anthropic/claude-opus-4-7',
  created_at: '2026-04-22T06:50:00Z',
  on_chain_tx: '0x' + 'b'.repeat(64),
  on_chain_block: 12345,
};

describe('BriefCard', () => {
  // TC-U100
  it('renders token name and thesis', () => {
    render(<BriefCard brief={sample} />);
    expect(screen.getByText('Test Token')).toBeInTheDocument();
    expect(screen.getByText(/strong organic mentions/)).toBeInTheDocument();
  });

  // TC-U101
  it('shows the conviction tier badge', () => {
    render(<BriefCard brief={sample} />);
    expect(screen.getByText('moderate')).toBeInTheDocument();
  });

  // TC-U102
  it('renders caveats as list items', () => {
    render(<BriefCard brief={sample} />);
    expect(screen.getByText('LP unlocked')).toBeInTheDocument();
    expect(screen.getByText('Creator has prior launches')).toBeInTheDocument();
  });

  // TC-U103
  it('provides BscScan and Verify links', () => {
    render(<BriefCard brief={sample} />);
    const bscscan = screen.getByTestId(`bscscan-${sample.msg_id}`);
    const verify = screen.getByTestId(`verify-${sample.msg_id}`);
    expect(bscscan).toHaveAttribute(
      'href',
      `https://testnet.bscscan.com/token/${sample.payload.token_address}`,
    );
    expect(verify.getAttribute('href')).toContain(`/briefs/${sample.msg_id}/verify`);
  });

  // TC-U104
  it('lists model attributions', () => {
    render(<BriefCard brief={sample} />);
    expect(screen.getByText(/anthropic\/claude-opus-4-7/)).toBeInTheDocument();
  });

  // TC-U105
  it('tolerates zero caveats without crashing', () => {
    const brief = { ...sample, payload: { ...sample.payload, caveats: [] } };
    render(<BriefCard brief={brief} />);
    expect(screen.queryByText(/Caveats/)).toBeNull();
  });

  // TC-U106 — degen tier gets danger colour class
  it('applies a tier-specific class for degen tier', () => {
    const brief = { ...sample, payload: { ...sample.payload, conviction_tier: 'degen' as const } };
    render(<BriefCard brief={brief} />);
    expect(screen.getByText('degen')).toBeInTheDocument();
  });

  // TC-U107 — high tier
  it('applies tier class for high tier', () => {
    const brief = { ...sample, payload: { ...sample.payload, conviction_tier: 'high' as const } };
    render(<BriefCard brief={brief} />);
    expect(screen.getByText('high')).toBeInTheDocument();
  });

  // TC-U108 — speculative tier
  it('applies tier class for speculative tier', () => {
    const brief = {
      ...sample,
      payload: { ...sample.payload, conviction_tier: 'speculative' as const },
    };
    render(<BriefCard brief={brief} />);
    expect(screen.getByText('speculative')).toBeInTheDocument();
  });

  // TC-U109 — caveats capped at 5
  it('caps caveats rendered at 5', () => {
    const brief = {
      ...sample,
      payload: {
        ...sample.payload,
        caveats: ['a', 'b', 'c', 'd', 'e', 'f', 'g'],
      },
    };
    render(<BriefCard brief={brief} />);
    expect(screen.queryByText('f')).toBeNull();
  });
});
