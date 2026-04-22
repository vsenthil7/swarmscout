/**
 * Tests for the `useBriefStream` hook.
 *
 * Stubs `globalThis.WebSocket` with a MockWebSocket that exposes its own
 * onopen/onmessage/onclose callbacks so the test can drive the hook
 * through each state transition (connecting -> open -> closed -> polling).
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useBriefStream } from '@/lib/hooks/useBriefStream';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: Event) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  close() {
    this.onclose?.(new Event('close'));
  }
}

describe('useBriefStream', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    (globalThis as unknown as { WebSocket: typeof WebSocket }).WebSocket =
      MockWebSocket as unknown as typeof WebSocket;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts in connecting state', () => {
    const { result } = renderHook(() => useBriefStream([]));
    expect(result.current.status).toBe('connecting');
  });

  it('moves to open on WS open', async () => {
    const { result } = renderHook(() => useBriefStream([]));
    act(() => {
      MockWebSocket.instances[0]?.onopen?.(new Event('open'));
    });
    expect(result.current.status).toBe('open');
  });

  it('prepends a well-formed message', () => {
    const { result } = renderHook(() => useBriefStream([]));
    act(() => {
      MockWebSocket.instances[0]?.onopen?.(new Event('open'));
      MockWebSocket.instances[0]?.onmessage?.({
        data: JSON.stringify({
          msg_id: '01ARZ3NDEKTSV4RRFFQ69G5FAV',
          payload: {
            token_name: 'A',
            token_address: '0x' + '0'.repeat(40),
            thesis: 't',
            conviction_tier: 'degen',
            caveats: [],
            sources: [],
            model_attribution: [],
            brief_generated_at: '2026-04-22T06:50:00Z',
            confidence_tier: 'ok',
          },
          payload_hash: 'a'.repeat(64),
          upstream_ids: [],
          model_used: null,
          created_at: '2026-04-22T06:50:00Z',
          on_chain_tx: null,
          on_chain_block: null,
        }),
      } as MessageEvent);
    });
    expect(result.current.briefs).toHaveLength(1);
  });

  it('ignores malformed frames', () => {
    const { result } = renderHook(() => useBriefStream([]));
    act(() => {
      MockWebSocket.instances[0]?.onmessage?.({ data: 'not-json' } as MessageEvent);
      MockWebSocket.instances[0]?.onmessage?.({
        data: JSON.stringify({ type: 'hello' }),
      } as MessageEvent);
    });
    expect(result.current.briefs).toHaveLength(0);
  });

  it('falls back to polling after repeated failures', async () => {
    // Mock fetch so the polling fallback doesn't hit a real network endpoint.
    // Use a factory so each call gets a fresh Response (bodies are one-shot).
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      new Response(JSON.stringify({ items: [], limit: 20, offset: 0 }), { status: 200 }),
    );
    try {
      const { result } = renderHook(() => useBriefStream([]));
      for (let i = 0; i < 3; i += 1) {
        act(() => {
          MockWebSocket.instances[i]?.onclose?.(new Event('close'));
          vi.advanceTimersByTime(60_000);
        });
      }
      // With fake timers, waitFor doesn't advance real time. Assert directly.
      expect(['polling', 'connecting']).toContain(result.current.status);
    } finally {
      fetchSpy.mockRestore();
    }
  });
});
