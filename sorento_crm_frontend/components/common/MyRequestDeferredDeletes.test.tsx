/**
 * PORTAL-P4-REQUESTS D7 red tests (crew answer a85478781): a salesperson's destructive actions on
 * the CRM request pages are server-deferred pending actions, never an immediate my-requests DELETE.
 *
 *  - MyRequestActions "Delete" on a draft  -> my_request.delete   (props: kind + requestId replace onDelete)
 *  - OwnAttachmentDelete on an own upload  -> my_request_attachment.unlink
 * Each shows a countdown with a Cancel; Escape does not cancel.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Sam Sales' } }, status: 'authenticated' }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: vi.fn(() => 'toast-1'),
  dismissDeferredToast: vi.fn(),
}));

const pending = vi.hoisted(() => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(),
}));
vi.mock('@/services/pendingActionService', () => pending);

const mine = vi.hoisted(() => ({
  deleteDraftSubmission: vi.fn(),
  deleteAttachment: vi.fn(),
  uploadAttachment: vi.fn(),
}));
vi.mock('@/services/myRequestsService', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  ...mine,
}));

import { MyRequestActions } from './MyRequestActions';
import { OwnAttachmentDelete } from './OwnRequestAttachmentActions';

function parked(key: string, type: string, id: string) {
  return {
    id: 'pa-1',
    action_key: key,
    entity_type: type,
    entity_id: id,
    commit_at: new Date(Date.now() + 10_000).toISOString().replace(/\.\d+Z$/, ''),
    window_seconds: 10,
  };
}

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  pending.getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
  pending.cancelPendingAction.mockResolvedValue(undefined);
});

describe('MyRequestActions: Delete draft is a deferred my_request.delete', () => {
  const props = {
    status: 'draft',
    revisable: false,
    busy: false,
    onEdit: vi.fn(),
    onRevise: vi.fn(),
    onDuplicate: vi.fn(),
    onSubmit: vi.fn(),
    // The coder drops this prop; a stale caller passing it must still never reach the DELETE.
    onDelete: vi.fn(),
    kind: 'complaint',
    requestId: 'req-1',
  } as unknown as React.ComponentProps<typeof MyRequestActions>;

  it('parks my_request.delete for the request and shows a countdown with Cancel', async () => {
    pending.createPendingAction.mockResolvedValue(parked('my_request.delete', 'complaint', 'req-1'));
    wrap(<MyRequestActions {...props} />);
    fireEvent.click(screen.getByRole('button', { name: /delete/i }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'my_request.delete',
          entityType: 'complaint',
          entityId: 'req-1',
        }),
      ),
    );
    expect(await screen.findByRole('timer')).toBeTruthy();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeTruthy();
    expect(mine.deleteDraftSubmission).not.toHaveBeenCalled();
    expect((props as { onDelete: () => void }).onDelete).not.toHaveBeenCalled();
  });

  it('Cancel withdraws the parked action; Escape does not', async () => {
    pending.createPendingAction.mockResolvedValue(parked('my_request.delete', 'complaint', 'req-1'));
    wrap(<MyRequestActions {...props} />);
    fireEvent.click(screen.getByRole('button', { name: /delete/i }));
    const cancel = await screen.findByRole('button', { name: /cancel/i });
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(pending.cancelPendingAction).not.toHaveBeenCalled();
    fireEvent.click(cancel);
    await waitFor(() => expect(pending.cancelPendingAction).toHaveBeenCalledWith('pa-1'));
  });

  it('shows no Delete once the request is no longer a draft', () => {
    wrap(<MyRequestActions {...props} status="submitted" />);
    expect(screen.queryByRole('button', { name: /delete/i })).toBeNull();
  });
});

describe('OwnAttachmentDelete: removing an own upload is a deferred my_request_attachment.unlink', () => {
  it('parks the unlink for the link id, with a countdown and Cancel, and never calls DELETE', async () => {
    pending.createPendingAction.mockResolvedValue(
      parked('my_request_attachment.unlink', 'my_request_attachment', 'link-1'),
    );
    wrap(<OwnAttachmentDelete linkId="link-1" refreshKeys={[['complaint', 'req-1']]} />);
    fireEvent.click(screen.getByRole('button', { name: /delete|remove/i }));
    await waitFor(() =>
      expect(pending.createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'my_request_attachment.unlink',
          entityType: 'my_request_attachment',
          entityId: 'link-1',
        }),
      ),
    );
    expect(await screen.findByRole('timer')).toBeTruthy();
    fireEvent.keyDown(document.body, { key: 'Escape' });
    expect(pending.cancelPendingAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    await waitFor(() => expect(pending.cancelPendingAction).toHaveBeenCalledWith('pa-1'));
    expect(mine.deleteAttachment).not.toHaveBeenCalled();
  });
});
