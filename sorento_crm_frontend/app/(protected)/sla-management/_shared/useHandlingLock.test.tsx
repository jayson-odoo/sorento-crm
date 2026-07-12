/**
 * Tests for the real `useHandlingLock` hook (Phase 2 — off mocks).
 *
 * Verifies the hook:
 *  - sources the active (first unresolved) tracker from `getFormHandlingTrackers`,
 *  - maps the API row (`tracking_id` → lock `id`) and feeds `resolveHandlingLockState`
 *    with the viewer-scoped `viewer_eligible` / `viewer_is_admin` / `flag_enabled`,
 *  - passes the CURRENT holder's `handled_by_id` as the take-over `expected_handler_id`
 *    (optimistic-concurrency guard — the backend 409s on a null/mismatched expectation).
 *
 * The pure resolver + banner are covered by handlingLock.test.ts / HandlingLockBanner.test.tsx.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import { useHandlingLock } from './useHandlingLock';
import type { FormHandlingTracker } from './formSLAService';

const getFormHandlingTrackers = vi.fn();
const claimHandling = vi.fn();
const takeOverHandling = vi.fn();
const releaseHandling = vi.fn();

vi.mock('./formSLAService', () => ({
  getFormHandlingTrackers: (...a: unknown[]) => getFormHandlingTrackers(...a),
  claimHandling: (...a: unknown[]) => claimHandling(...a),
  takeOverHandling: (...a: unknown[]) => takeOverHandling(...a),
  releaseHandling: (...a: unknown[]) => releaseHandling(...a),
}));

let effectiveUserId: string | null = 'me';
vi.mock('@/hooks/useEffectiveUserId', () => ({
  useEffectiveUserId: () => effectiveUserId,
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function row(partial: Partial<FormHandlingTracker> = {}): FormHandlingTracker {
  return {
    tracking_id: 'trk-1',
    current_tier: 2,
    due_at: null,
    due_at_resolution: null,
    is_resolved: false,
    assigned_to_id: 'assignee-1',
    assigned_to_name: 'Assignee',
    source_entity_type: 'complaint',
    source_entity_id: 'cmp-1',
    escalation_reason: null,
    handled_by_id: null,
    handled_by_name: null,
    handled_at: null,
    flag_enabled: true,
    viewer_eligible: true,
    viewer_is_admin: false,
    ...partial,
  };
}

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  getFormHandlingTrackers.mockReset();
  claimHandling.mockReset();
  takeOverHandling.mockReset();
  releaseHandling.mockReset();
  effectiveUserId = 'me';
});

describe('useHandlingLock', () => {
  it('resolves "unclaimed" from an escalated + eligible + unheld tracker', async () => {
    getFormHandlingTrackers.mockResolvedValue([row({ handled_by_id: null })]);
    const { result } = renderHook(
      () => useHandlingLock({ sourceEntityType: 'complaint', sourceEntityId: 'cmp-1' }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.state).toBe('unclaimed'));
    expect(result.current.businessCtasEnabled).toBe(false);
    // tracking_id is mapped onto the lock tracker's id.
    expect(result.current.tracker?.id).toBe('trk-1');
    expect(getFormHandlingTrackers).toHaveBeenCalledWith('complaint', 'cmp-1');
  });

  it('resolves "mine" and enables CTAs when I hold the lock', async () => {
    getFormHandlingTrackers.mockResolvedValue([
      row({ handled_by_id: 'me', handled_by_name: 'You', handled_at: '2026-07-09T01:30:00' }),
    ]);
    const { result } = renderHook(
      () => useHandlingLock({ sourceEntityType: 'complaint', sourceEntityId: 'cmp-1' }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.state).toBe('mine'));
    expect(result.current.businessCtasEnabled).toBe(true);
  });

  it('take-over passes the CURRENT holder id as expected_handler_id', async () => {
    getFormHandlingTrackers.mockResolvedValue([
      row({ handled_by_id: 'jane', handled_by_name: 'Jane Tan' }),
    ]);
    takeOverHandling.mockResolvedValue(row({ handled_by_id: 'me' }));
    const { result } = renderHook(
      () => useHandlingLock({ sourceEntityType: 'complaint', sourceEntityId: 'cmp-1' }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.state).toBe('other_holds'));

    await act(async () => {
      result.current.takeOver();
    });

    expect(takeOverHandling).toHaveBeenCalledWith('trk-1', 'jane');
  });

  it('picks the first UNRESOLVED row as the active tracker', async () => {
    getFormHandlingTrackers.mockResolvedValue([
      row({ tracking_id: 'resolved', is_resolved: true }),
      row({ tracking_id: 'active', handled_by_id: null }),
    ]);
    const { result } = renderHook(
      () => useHandlingLock({ sourceEntityType: 'complaint', sourceEntityId: 'cmp-1' }),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.tracker?.id).toBe('active'));
  });

  it('does not query (state not_escalated) when the entity id is null', async () => {
    const { result } = renderHook(
      () => useHandlingLock({ sourceEntityType: 'complaint', sourceEntityId: null }),
      { wrapper: wrapper() },
    );
    expect(result.current.state).toBe('not_escalated');
    expect(getFormHandlingTrackers).not.toHaveBeenCalled();
  });
});
