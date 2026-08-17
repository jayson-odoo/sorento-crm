import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SendTemplateDialog from './SendTemplateDialog';

vi.mock('@/services/whatsappTemplateService', async () => {
  const actual = await vi.importActual<
    typeof import('@/services/whatsappTemplateService')
  >('@/services/whatsappTemplateService');
  return {
    ...actual,
    listApprovedTemplates: vi.fn(),
    sendTemplateMessage: vi.fn(),
  };
});

import {
  listApprovedTemplates,
  sendTemplateMessage,
} from '@/services/whatsappTemplateService';

const TEMPLATE = {
  id: 'tpl-1',
  respond_template_id: 'rt-1',
  name: 'update',
  language: 'en',
  category: 'UTILITY',
  status: 'approved' as const,
  body_text: 'Hi {{1}}, update: {{2}}',
  param_count: 2,
  channel_name: 'WA',
  synced_at: '2026-06-08T00:00:00Z',
};

function renderDialog(props: Partial<React.ComponentProps<typeof SendTemplateDialog>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SendTemplateDialog
        entityType="complaint"
        entityId="c1"
        contactId="contact-1"
        open
        onOpenChange={() => {}}
        {...props}
      />
    </QueryClientProvider>,
  );
}

describe('SendTemplateDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (listApprovedTemplates as any).mockResolvedValue([TEMPLATE]);
  });

  it('lists approved templates in the picker', async () => {
    renderDialog();
    expect(await screen.findByTestId('template-option-update')).toBeInTheDocument();
  });

  it('matches snake_case names from a separator-free / spaced query', async () => {
    (listApprovedTemplates as any).mockResolvedValue([
      { ...TEMPLATE, id: 'tpl-cfu', name: 'conversation_follow_up' },
      { ...TEMPLATE, id: 'tpl-upd', name: 'order_update' },
    ]);
    renderDialog();
    const search = await screen.findByPlaceholderText('Search templates...');

    fireEvent.change(search, { target: { value: 'conversation follow up' } });
    expect(screen.getByTestId('template-option-conversation_follow_up')).toBeInTheDocument();
    expect(screen.queryByTestId('template-option-order_update')).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'conversationfollowup' } });
    expect(screen.getByTestId('template-option-conversation_follow_up')).toBeInTheDocument();
  });

  it('shows empty state when no approved templates exist', async () => {
    (listApprovedTemplates as any).mockResolvedValue([]);
    renderDialog();
    expect(await screen.findByText(/No approved templates available/i)).toBeInTheDocument();
  });

  it('keeps Send disabled until all params are filled, then live-previews', async () => {
    renderDialog();
    fireEvent.click(await screen.findByTestId('template-option-update'));

    const sendBtn = await screen.findByRole('button', { name: /^Send template$/i });
    expect(sendBtn).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('Value for {{1}}'), {
      target: { value: 'Ms Ang' },
    });
    fireEvent.change(screen.getByPlaceholderText('Value for {{2}}'), {
      target: { value: 'approved' },
    });

    expect(screen.getByText('Hi Ms Ang, update: approved')).toBeInTheDocument();
    expect(sendBtn).toBeEnabled();
  });

  it('sends the template with positional params on submit', async () => {
    (sendTemplateMessage as any).mockResolvedValue({ ok: true });
    const onSent = vi.fn();
    renderDialog({ onSent });

    fireEvent.click(await screen.findByTestId('template-option-update'));
    fireEvent.change(screen.getByPlaceholderText('Value for {{1}}'), {
      target: { value: 'Ms Ang' },
    });
    fireEvent.change(screen.getByPlaceholderText('Value for {{2}}'), {
      target: { value: 'approved' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Send template$/i }));

    await waitFor(() => expect(sendTemplateMessage).toHaveBeenCalledTimes(1));
    expect(sendTemplateMessage).toHaveBeenCalledWith('complaint', 'c1', {
      contact_id: 'contact-1',
      template_id: 'tpl-1',
      params: { '1': 'Ms Ang', '2': 'approved' },
      // No intervention ticket on this surface: only the ticket drawer sets it.
      tracking_id: null,
    });
    await waitFor(() => expect(onSent).toHaveBeenCalled());
  });

  it('a sendAdapter takes over the send entirely (the contact-keyed inbox route)', async () => {
    const sendAdapter = vi.fn().mockResolvedValue({ ok: true });
    const onSent = vi.fn();
    renderDialog({ sendAdapter, onSent });

    fireEvent.click(await screen.findByTestId('template-option-update'));
    fireEvent.change(screen.getByPlaceholderText('Value for {{1}}'), {
      target: { value: 'Ms Ang' },
    });
    fireEvent.change(screen.getByPlaceholderText('Value for {{2}}'), {
      target: { value: 'approved' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Send template$/i }));

    await waitFor(() =>
      expect(sendAdapter).toHaveBeenCalledWith({
        template_id: 'tpl-1',
        params: { '1': 'Ms Ang', '2': 'approved' },
      }),
    );
    // The entity chat route is not a fallback here: it does not exist for a
    // contact-keyed surface and calling it would 404 (or throw on chatBase).
    expect(sendTemplateMessage).not.toHaveBeenCalled();
    await waitFor(() => expect(onSent).toHaveBeenCalled());
  });
});
