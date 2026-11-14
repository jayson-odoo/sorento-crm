/**
 * OCN-ORDER-CHANGE-NOTICE round 3 (owner: full purchase request parity, "all the SLA"): a stage
 * move held for its grace window behaves as on the purchase request detail. The shared
 * `useFormAction` family drives it: the detail shows the countdown banner with Undo, the workflow
 * buttons wait, and no success is claimed until the action has really applied. Grace off, the
 * move applies at once with its success toast.
 *
 * `useFormAction` is stubbed at its boundary (its view and refresh are what the detail reads);
 * the banner is the real shared one. The service is mocked at its boundary.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const state = vi.hoisted(() => ({
  perms: new Set<string>(),
  get: vi.fn(),
  send: vi.fn(),
  view: { kind: 'idle' } as Record<string, unknown>,
  ctasDisabled: false,
  refresh: vi.fn(),
  cancel: vi.fn(),
}));
const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => '/procurement-management/order-change-notices/x',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => state.perms.has(slug),
  usePermissions: () => ({ permissions: [], permissionSet: state.perms, isLoading: false }),
}));
vi.mock('@/hooks/useEffectiveUserId', () => ({ useEffectiveUserId: () => 'someone-else' }));
vi.mock('@/lib/toast', () => ({ toast: toasts }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => null }));
vi.mock('@/components/common/comments/FormComments', () => ({ FormComments: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/FormSLATrackingTab', () => ({ default: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/useHandlingLock', () => ({
  useHandlingLock: () => ({
    state: 'not_escalated', businessCtasEnabled: true, tracker: null, banner: null,
    claim: vi.fn(), takeOver: vi.fn(), release: vi.fn(), refresh: vi.fn(), isMutating: false,
  }),
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockBanner', () => ({ HandlingLockBanner: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockActions', () => ({
  HandlingLockReleaseMenuItem: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/useFormAction', () => ({
  useFormAction: () => ({
    view: state.view,
    ctasDisabled: state.ctasDisabled,
    cancel: state.cancel,
    undo: vi.fn(),
    refresh: state.refresh,
    isMutating: false,
  }),
}));
vi.mock('@/components/common/DetailActions', () => ({
  default: ({ gear, primary }: { gear?: React.ReactNode; primary?: React.ReactNode }) => (
    <div>
      {gear}
      {primary}
    </div>
  ),
}));
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/ui/dropdown-menu', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/ui/dropdown-menu')>();
  return {
    ...actual,
    DropdownMenuItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => (
      <button type="button" onClick={() => onSelect?.()}>{children}</button>
    ),
  };
});
vi.mock('../services/orderChangeNoticeService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderChangeNoticeService')>();
  return {
    ...actual,
    getOrderChangeNotice: (...a: unknown[]) => state.get(...a),
    sendForApproval: (...a: unknown[]) => state.send(...a),
  };
});

import { FORM_ACTION_FIXTURES } from '@/app/(protected)/sla-management/_shared/__mocks__/formActions';
import OrderChangeNoticeDetail from './OrderChangeNoticeDetail';
import { OCN_ID, ocnDetail } from './ocnTestData';

const EDIT = 'procurement.order_change_notices.edit';
const SUBMITTED = ocnDetail({ status: 'submitted', approval_status: null });

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <OrderChangeNoticeDetail ocnId={OCN_ID} />
    </QueryClientProvider>,
  );
  return screen.findByRole('heading', { name: /OCN26-0302/ });
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  state.perms = new Set(['procurement.order_change_notices.view', EDIT]);
  state.get.mockResolvedValue(SUBMITTED);
  state.view = { kind: 'idle' };
  state.ctasDisabled = false;
});
afterEach(() => cleanup());

describe('grace on: a held stage move', () => {
  it('claims no success, says it can still be undone, and asks the banner to refresh', async () => {
    state.send.mockResolvedValue({
      deferred: true,
      pending_action_id: 'pa-1',
      action_key: 'ocn.send_for_approval',
      commit_at: '2026-11-12T10:00:10',
      window_seconds: 10,
    });
    await mount();
    fireEvent.click(screen.getByRole('button', { name: /^send for approval$/i }));
    await waitFor(() => expect(state.refresh).toHaveBeenCalled());
    expect(state.send).toHaveBeenCalledWith(OCN_ID, 0);
    expect(toasts.success).not.toHaveBeenCalled();
    expect(toasts.info).toHaveBeenCalledWith(expect.stringMatching(/can still undo/i));
  });

  it('shows the countdown with Undo while it is held, and the workflow buttons wait', async () => {
    state.view = { kind: 'pending', action: FORM_ACTION_FIXTURES.pending.pending };
    state.ctasDisabled = true;
    await mount();
    expect(screen.getByTestId('form-action-banner')).toBeTruthy();
    const undo = screen.getByTestId('form-action-undo-pending');
    expect(screen.queryByRole('button', { name: /^send for approval$/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^send back$/i })).toBeNull();
    fireEvent.click(undo);
    expect(state.cancel).toHaveBeenCalled();
    expect(toasts.success).not.toHaveBeenCalled();
  });

  it('after it applies, the last action can be undone from the actions menu', async () => {
    state.view = { kind: 'undoable', eligibility: FORM_ACTION_FIXTURES.undoable.eligibility };
    await mount();
    expect(screen.getByRole('button', { name: /undo last action/i })).toBeTruthy();
  });
});

describe('grace off: the move applies at once', () => {
  it('shows its success toast and no countdown', async () => {
    state.send.mockResolvedValue(ocnDetail({ status: 'submitted', approval_status: 'pending' }));
    await mount();
    fireEvent.click(screen.getByRole('button', { name: /^send for approval$/i }));
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith('Sent for approval'));
    expect(state.refresh).not.toHaveBeenCalled();
    expect(toasts.info).not.toHaveBeenCalled();
    expect(screen.queryByTestId('form-action-banner')).toBeNull();
  });
});
