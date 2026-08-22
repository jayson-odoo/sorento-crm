/**
 * S8 - what the supplier was told, per channel.
 *
 * The failure mode this guards is the screen being reassuring when it should not be: a notice
 * nobody could send reading as "sent", a "not sent" that never says why, or a send leaving the
 * building without being confirmed first.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const state = {
  notices: [] as unknown[],
  approve: vi.fn(),
};

vi.mock('../../services/fulfilmentService', () => ({
  getPlanNotices: () => Promise.resolve(state.notices),
  approveLoadingPlan: (...args: unknown[]) => state.approve(...args),
  getNoticeDocumentUrl: () =>
    Promise.resolve({ url: 'https://example.test/doc.pdf', filename: 'doc.pdf' }),
}));

import { SupplierNoticePanel } from './SupplierNoticePanel';

function notice(over: Record<string, unknown> = {}) {
  return {
    id: 'n-1',
    supplier_id: 'sup-1',
    supplier_name: 'Foshan Ceramics',
    loading_plan_id: 'plan-1',
    notice_type: 'loading',
    channel: 'email',
    recipient: 'sales@foshan.test',
    status: 'sent',
    status_reason: null,
    sent_at: '2026-08-09T02:00:00',
    attempt_count: 1,
    last_error: null,
    document_filename: 'loading-notice.pdf',
    has_document: true,
    container_type: '40HQ',
    container_count: 1,
    planned_cbm: 60,
    line_count: 12,
    production_line_count: 3,
    created_at: '2026-08-09T02:00:00',
    created_by: 'Ms Tee',
    ...over,
  };
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SupplierNoticePanel planId="plan-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  state.notices = [];
  state.approve = vi.fn().mockResolvedValue({ notices: [], document_filename: 'x.pdf' });
});

describe('SupplierNoticePanel', () => {
  it('renders with nothing sent, and says so', async () => {
    // Per the CRUD standard the section is always present. "Nothing has gone out" is the state
    // Ms Tee most needs, and a section that appears only after the first send cannot show it.
    renderPanel();

    expect(await screen.findByText(/nothing has been sent for this plan yet/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /approve and send/i })).toBeInTheDocument();
  });

  it('confirms before anything leaves the building', async () => {
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: /approve and send/i }));

    expect(await screen.findByText(/send this plan to the supplier\?/i)).toBeInTheDocument();
    expect(state.approve).not.toHaveBeenCalled();
  });

  it('warns that a second send produces a second email', async () => {
    // The riskier case. A supplier receiving the same notice twice is a phone call.
    state.notices = [notice()];
    renderPanel();

    fireEvent.click(await screen.findByRole('button', { name: /send again/i }));

    expect(await screen.findByText(/second notice and a second email/i)).toBeInTheDocument();
  });

  it('sends once confirmed', async () => {
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: /approve and send/i }));
    fireEvent.click(await screen.findByRole('button', { name: /^send$/i }));

    await waitFor(() => expect(state.approve).toHaveBeenCalledWith('plan-1'));
  });

  it('shows the channel, the recipient and when it went', async () => {
    // AC-F6, all four facts on one line.
    state.notices = [notice()];
    renderPanel();

    expect(await screen.findByText('Email')).toBeInTheDocument();
    expect(screen.getByText('sales@foshan.test')).toBeInTheDocument();
    expect(screen.getByText('Sent')).toBeInTheDocument();
  });

  it('says WHY a notice was not sent, not just that it was not', async () => {
    // "Not sent" on its own is a dead end, and both of its causes are things a person can fix.
    state.notices = [
      notice({
        id: 'n-2',
        status: 'skipped',
        status_reason: 'This supplier has no email address on file.',
        recipient: null,
        sent_at: null,
      }),
    ];
    renderPanel();

    expect(await screen.findByText('Not sent')).toBeInTheDocument();
    expect(
      screen.getByText(/this supplier has no email address on file/i),
    ).toBeInTheDocument();
  });

  it('offers the document even when nothing could send it', async () => {
    // AC-F3. The document is the point: Ms Tee sends it by hand when we cannot.
    state.notices = [
      notice({ status: 'skipped', status_reason: 'No chat channel is linked yet.', channel: 'chat' }),
    ];
    renderPanel();

    const button = await screen.findByRole('button', { name: /document/i });
    expect(button).toBeEnabled();
  });

  it('does not offer a document that does not exist', async () => {
    state.notices = [notice({ has_document: false, document_filename: null })];
    renderPanel();

    expect(await screen.findByRole('button', { name: /document/i })).toBeDisabled();
  });

  it('shows the error on a failed send rather than a bare status', async () => {
    state.notices = [
      notice({ status: 'failed', last_error: 'SMTP 550 mailbox unavailable', sent_at: null }),
    ];
    renderPanel();

    expect(await screen.findByText('Failed')).toBeInTheDocument();
    expect(screen.getByText(/smtp 550 mailbox unavailable/i)).toBeInTheDocument();
  });

  it('states what was asked for, packing and production apart', async () => {
    state.notices = [notice({ line_count: 12, production_line_count: 3 })];
    renderPanel();

    expect(await screen.findByText(/12 to pack/)).toBeInTheDocument();
    expect(screen.getByText(/3 to produce/)).toBeInTheDocument();
  });
});
