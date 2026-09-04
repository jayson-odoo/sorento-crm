/**
 * Tests for `useFormSkip` - the config-driven skip capability (UAC C1/C2/C4/C5).
 *
 * The hook decides whether a form's gear menu offers a skip action at all, so the
 * cases that matter most are the ones where it must say NO: a stage that declares no
 * skip, a viewer without the permission, a resolved tracker, no tracker at all.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';

import { useFormSkip } from './useFormSkip';
import type { FormHandlingTracker } from './formSLAService';

const getFormHandlingTrackers = vi.fn();
const skipFormStage = vi.fn();

vi.mock('./formSLAService', () => ({
  getFormHandlingTrackers: (...a: unknown[]) => getFormHandlingTrackers(...a),
}));
vi.mock('./formSkipService', () => ({
  skipFormStage: (...a: unknown[]) => skipFormStage(...a),
}));

let hasPermission = true;
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => hasPermission,
}));

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

const PERM = 'complaint_management.complaints.settle_on_site';

function row(partial: Partial<FormHandlingTracker> = {}): FormHandlingTracker {
  return {
    tracking_id: 'trk-1',
    current_tier: 1,
    due_at: null,
    due_at_resolution: null,
    is_resolved: false,
    assigned_to_id: null,
    assigned_to_name: null,
    source_entity_type: 'complaint',
    source_entity_id: 'c-1',
    escalation_reason: null,
    escalated_at: null,
    handled_by_id: null,
    handled_by_name: null,
    handled_at: null,
    flag_enabled: false,
    skip_event: 'settled_on_site',
    skip_action_label: 'Settled on site',
    can_skip: true,
    ...partial,
  } as FormHandlingTracker;
}

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function render(overrides: Partial<Parameters<typeof useFormSkip>[0]> = {}) {
  return renderHook(
    () =>
      useFormSkip({
        sourceEntityType: 'complaint',
        sourceEntityId: 'c-1',
        permission: PERM,
        ...overrides,
      }),
    { wrapper },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  hasPermission = true;
  getFormHandlingTrackers.mockResolvedValue([row()]);
  skipFormStage.mockResolvedValue({
    status: 'settled_on_site',
    resolved_at: '2026-08-03T02:15:00',
    message: 'Complaint marked as settled on site.',
  });
});

describe('useFormSkip - when the action is offered (C1)', () => {
  it('offers the skip with the config-authored label', async () => {
    const { result } = render();
    await waitFor(() => expect(result.current.canSkip).toBe(true));
    expect(result.current.actionLabel).toBe('Settled on site');
  });
});

describe('useFormSkip - when the action is withheld (C2)', () => {
  it('withholds it when the stage declares no skip', async () => {
    getFormHandlingTrackers.mockResolvedValue([
      row({ skip_event: null, skip_action_label: null, can_skip: false }),
    ]);
    const { result } = render();
    await waitFor(() => expect(getFormHandlingTrackers).toHaveBeenCalled());
    expect(result.current.canSkip).toBe(false);
  });

  it('withholds it when the viewer lacks the permission', async () => {
    hasPermission = false;
    const { result } = render();
    await waitFor(() => expect(getFormHandlingTrackers).toHaveBeenCalled());
    expect(result.current.canSkip).toBe(false);
  });

  it("withholds it when the server says the viewer can't skip", async () => {
    // Server verdict is authoritative even if the client thinks it holds the perm.
    getFormHandlingTrackers.mockResolvedValue([row({ can_skip: false })]);
    const { result } = render();
    await waitFor(() => expect(getFormHandlingTrackers).toHaveBeenCalled());
    expect(result.current.canSkip).toBe(false);
  });

  it('withholds it when every tracker is resolved', async () => {
    getFormHandlingTrackers.mockResolvedValue([row({ is_resolved: true })]);
    const { result } = render();
    await waitFor(() => expect(getFormHandlingTrackers).toHaveBeenCalled());
    expect(result.current.canSkip).toBe(false);
  });

  it('withholds it when there is no tracker at all', async () => {
    getFormHandlingTrackers.mockResolvedValue([]);
    const { result } = render();
    await waitFor(() => expect(getFormHandlingTrackers).toHaveBeenCalled());
    expect(result.current.canSkip).toBe(false);
  });

  it('withholds it and does not query when disabled by the caller', async () => {
    const { result } = render({ enabled: false });
    expect(result.current.canSkip).toBe(false);
    expect(getFormHandlingTrackers).not.toHaveBeenCalled();
  });
});

describe('useFormSkip - submitting (C4/C5)', () => {
  it('posts the note, toasts, and reports the result to the caller', async () => {
    const onSkipped = vi.fn();
    const { result } = render({ onSkipped });
    await waitFor(() => expect(result.current.canSkip).toBe(true));

    await act(async () => {
      result.current.submit('Replaced the seal on site.');
    });

    await waitFor(() => expect(skipFormStage).toHaveBeenCalled());
    expect(skipFormStage).toHaveBeenCalledWith('complaint', 'c-1', {
      note: 'Replaced the seal on site.',
    });
    await waitFor(() => expect(onSkipped).toHaveBeenCalled());
    expect(toastSuccess).toHaveBeenCalledWith('Complaint marked as settled on site.');
  });

  it('omits the note entirely when none was given', async () => {
    const { result } = render();
    await waitFor(() => expect(result.current.canSkip).toBe(true));
    await act(async () => {
      result.current.submit();
    });
    await waitFor(() => expect(skipFormStage).toHaveBeenCalledWith('complaint', 'c-1', {}));
  });

  it("surfaces the backend's message and does not tell the caller it succeeded", async () => {
    const onSkipped = vi.fn();
    skipFormStage.mockRejectedValue(
      new Error('This form is being handled by Nurul. Take over to act.'),
    );
    const { result } = render({ onSkipped });
    await waitFor(() => expect(result.current.canSkip).toBe(true));

    await act(async () => {
      result.current.submit();
    });

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        'This form is being handled by Nurul. Take over to act.',
      ),
    );
    expect(onSkipped).not.toHaveBeenCalled();
    expect(toastSuccess).not.toHaveBeenCalled();
  });
});
