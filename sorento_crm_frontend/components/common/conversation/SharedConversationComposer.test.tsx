import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SharedConversationComposer from './SharedConversationComposer';

// Keep the real module (so NoChatTemplateError stays the SAME class the composer
// catches with `instanceof`) but stub the network functions.
vi.mock('@/services/whatsappTemplateService', async () => {
  const actual = await vi.importActual<
    typeof import('@/services/whatsappTemplateService')
  >('@/services/whatsappTemplateService');
  return {
    ...actual,
    getWindowState: vi.fn(),
    sendConversationMessage: vi.fn(),
    getChatTemplatePreview: vi.fn(),
    listApprovedTemplates: vi.fn().mockResolvedValue([]),
    sendTemplateMessage: vi.fn(),
  };
});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import {
  getWindowState,
  sendConversationMessage,
  getChatTemplatePreview,
  listApprovedTemplates,
  sendTemplateMessage,
  NoChatTemplateError,
} from '@/services/whatsappTemplateService';
import { toast } from '@/lib/toast';

// jsdom does not implement scrollIntoView (guard per CLAUDE.md).
if (!(Element.prototype as any).scrollIntoView) {
  (Element.prototype as any).scrollIntoView = vi.fn();
}

function renderComposer(
  props: Partial<React.ComponentProps<typeof SharedConversationComposer>> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SharedConversationComposer
        entityType="complaint"
        entityId="c1"
        canReply
        {...props}
      />
    </QueryClientProvider>,
  );
}

const OPEN = { open: true, last_incoming_at: null, checked_at: '2026-07-01T00:00:00Z' };
const CLOSED = { open: false, last_incoming_at: null, checked_at: '2026-07-01T00:00:00Z' };

// Out-of-window template preview: the `*_chat` template rendered inline with a
// fill-in field. Slot "1" resolves to the sender name (read-only); slot "2" is
// the editable message field.
const PREVIEW_CONFIGURED = {
  configured: true,
  template_name: 't',
  body_text: 'Hi {{1}}: {{2}}',
  slots: {
    '1': { variable: 'sender_name', value: 'Admin', editable: false },
    '2': { variable: 'message', value: null, editable: true },
  },
};

const PREVIEW_UNCONFIGURED = {
  configured: false,
  settings_url: '/integration-management/whatsapp-templates',
};

describe('SharedConversationComposer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getWindowState as any).mockResolvedValue(OPEN);
    (getChatTemplatePreview as any).mockResolvedValue(PREVIEW_CONFIGURED);
    (sendConversationMessage as any).mockResolvedValue({
      sent_as: 'text',
      rendered_text: 'hi there',
      flattened: false,
      window_state: OPEN,
    });
  });

  // ----------------------------------------------------------------- in-window

  it('in-window: plain textbox present; preview query disabled (not called)', async () => {
    (getWindowState as any).mockResolvedValue(OPEN);
    renderComposer();

    await waitFor(() => expect(getWindowState).toHaveBeenCalled());
    expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    // Window open -> the template preview query is disabled and never fires.
    expect(getChatTemplatePreview).not.toHaveBeenCalled();
    // No template-mode surface in-window.
    expect(screen.queryByTestId('composer-template-mode')).not.toBeInTheDocument();
  });

  it('in-window: typing + Enter (no shift) sends via the API', async () => {
    (getWindowState as any).mockResolvedValue(OPEN);
    renderComposer();

    await waitFor(() => expect(getWindowState).toHaveBeenCalled());
    const textarea = screen.getByPlaceholderText('Type your message...');
    fireEvent.change(textarea, { target: { value: 'hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    await waitFor(() =>
      expect(sendConversationMessage).toHaveBeenCalledWith('complaint', 'c1', 'hello'),
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Message sent'));
  });

  it('in-window: clicking Send sends via the API', async () => {
    (getWindowState as any).mockResolvedValue(OPEN);
    renderComposer();

    await waitFor(() => expect(getWindowState).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText('Type your message...'), {
      target: { value: 'hey there' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() =>
      expect(sendConversationMessage).toHaveBeenCalledWith('complaint', 'c1', 'hey there'),
    );
  });

  // ---------------------------------------------------- out-of-window: template

  it('out-of-window: renders the template inline with a fill-in field and no plain textbox', async () => {
    (getWindowState as any).mockResolvedValue(CLOSED);
    (getChatTemplatePreview as any).mockResolvedValue(PREVIEW_CONFIGURED);
    renderComposer();

    expect(await screen.findByTestId('composer-template-mode')).toBeInTheDocument();
    expect(screen.getByTestId('template-message-field')).toBeInTheDocument();
    // The plain in-window textbox is NOT rendered in template mode.
    expect(screen.queryByPlaceholderText('Type your message...')).not.toBeInTheDocument();
    // Resolved non-message value shown read-only in the preview.
    expect(screen.getByText('Admin')).toBeInTheDocument();
    expect(getChatTemplatePreview).toHaveBeenCalledWith('complaint', 'c1');
  });

  it('out-of-window: a newline in the message field shows the flatten warning; a single line does not', async () => {
    (getWindowState as any).mockResolvedValue(CLOSED);
    (getChatTemplatePreview as any).mockResolvedValue(PREVIEW_CONFIGURED);
    renderComposer();

    const field = await screen.findByTestId('template-message-field');

    fireEvent.change(field, { target: { value: 'line one\nline two' } });
    expect(screen.getByTestId('flatten-warning')).toBeInTheDocument();

    fireEvent.change(field, { target: { value: 'one line' } });
    expect(screen.queryByTestId('flatten-warning')).not.toBeInTheDocument();
  });

  it('out-of-window: clicking Send sends the field text via the API', async () => {
    (getWindowState as any).mockResolvedValue(CLOSED);
    (getChatTemplatePreview as any).mockResolvedValue(PREVIEW_CONFIGURED);
    (sendConversationMessage as any).mockResolvedValue({
      sent_as: 'template',
      rendered_text: 'Hi Admin: my reply',
      flattened: false,
      window_state: CLOSED,
    });
    renderComposer();

    const field = await screen.findByTestId('template-message-field');
    fireEvent.change(field, { target: { value: 'my reply' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() =>
      expect(sendConversationMessage).toHaveBeenCalledWith('complaint', 'c1', 'my reply'),
    );
  });

  // ------------------------------------------------ out-of-window: no template

  it('out-of-window, no template configured: shows the notice UPFRONT with a settings link (before any send)', async () => {
    (getWindowState as any).mockResolvedValue(CLOSED);
    (getChatTemplatePreview as any).mockResolvedValue(PREVIEW_UNCONFIGURED);
    renderComposer();

    const notice = await screen.findByTestId('no-chat-template-notice');
    expect(notice).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /configure a chat reply template/i });
    expect(link).toHaveAttribute('href', '/integration-management/whatsapp-templates');
    // Shown upfront - no send was attempted.
    expect(sendConversationMessage).not.toHaveBeenCalled();
  });

  it('send-time fallback: a NoChatTemplateError surfaces the notice', async () => {
    (getWindowState as any).mockResolvedValue(CLOSED);
    (getChatTemplatePreview as any).mockResolvedValue(PREVIEW_CONFIGURED);
    (sendConversationMessage as any).mockRejectedValue(
      new NoChatTemplateError(
        'No chat reply template configured for this form.',
        '/integration-management/whatsapp-templates',
      ),
    );
    renderComposer();

    const field = await screen.findByTestId('template-message-field');
    fireEvent.change(field, { target: { value: 'hi' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    const notice = await screen.findByTestId('no-chat-template-notice');
    expect(notice).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /configure a chat reply template/i });
    expect(link).toHaveAttribute('href', '/integration-management/whatsapp-templates');
  });

  // --------------------------------------------------------------- mode gating

  it('conversation mode hides entity-only affordances', async () => {
    renderComposer({
      mode: 'conversation',
      onGetViewLink: async () => 'https://x/link',
      useResponseText: 'canned reply',
    });
    await waitFor(() => expect(getWindowState).toHaveBeenCalled());
    expect(screen.queryByRole('button', { name: /attach view link/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /use response/i })).not.toBeInTheDocument();
  });

  it('entity mode renders the view-link + use-response affordances', async () => {
    renderComposer({
      mode: 'entity',
      onGetViewLink: async () => 'https://x/link',
      useResponseText: 'canned reply',
    });
    expect(await screen.findByRole('button', { name: /attach view link/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /use response/i })).toBeInTheDocument();
  });

  // ------------------------------------------------ partial attachment failure

  /** Stage `names` on the composer's hidden file input. */
  function attach(names: string[]) {
    const input = screen.getByTestId('composer-file-input') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: names.map((n) => new File(['x'], n, { type: 'application/pdf' })) },
    });
  }

  it('FINDING 3: a partial multi-file send clears only the delivered files', async () => {
    const sendAdapter = vi.fn().mockResolvedValue({
      sent_as: 'attachment',
      attachments: {
        delivered: ['a.pdf'],
        failed: { filename: 'b.pdf', error: 'Respond 500 unavailable' },
      },
    });
    renderComposer({ mode: 'conversation', attachmentsEnabled: true, sendAdapter });
    await waitFor(() => expect(screen.getByTestId('composer-file-input')).toBeInTheDocument());

    attach(['a.pdf', 'b.pdf', 'c.pdf']);
    expect(screen.getByTestId('composer-attachments').textContent).toContain('a.pdf');

    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }));

    await waitFor(() => expect(sendAdapter).toHaveBeenCalled());
    // a.pdf reached the contact -> gone. b.pdf failed and c.pdf was never
    // attempted -> both stay staged so a retry cannot double-send a.pdf.
    await waitFor(() => {
      const staged = screen.getByTestId('composer-attachments').textContent ?? '';
      expect(staged).not.toContain('a.pdf');
      expect(staged).toContain('b.pdf');
      expect(staged).toContain('c.pdf');
    });
    // The failed one is marked, and the toast names it.
    expect(screen.getByTestId('composer-attachment-failed').textContent).toContain('b.pdf');
    expect(toast.error).toHaveBeenCalledWith(
      'b.pdf was not sent: Respond 500 unavailable',
    );
  });

  it('FINDING 3: an all-delivered send clears every file and marks nothing failed', async () => {
    const sendAdapter = vi.fn().mockResolvedValue({
      sent_as: 'attachment',
      attachments: { delivered: ['a.pdf', 'b.pdf'], failed: null },
    });
    renderComposer({ mode: 'conversation', attachmentsEnabled: true, sendAdapter });
    await waitFor(() => expect(screen.getByTestId('composer-file-input')).toBeInTheDocument());

    attach(['a.pdf', 'b.pdf']);
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }));

    await waitFor(() => expect(sendAdapter).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByTestId('composer-attachments')).not.toBeInTheDocument(),
    );
    expect(screen.queryByTestId('composer-attachment-failed')).not.toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('a send that reports NO delivered attachment is an error, not a silent success', async () => {
    // The backend degraded to a text-only send (its multipart parsing dropped
    // the file) and still answered 200. Clearing the chips here is what made
    // that invisible: the operator saw "Message sent" and the contact got
    // nothing. Files stay staged; the text did go out, so the box clears.
    const sendAdapter = vi.fn().mockResolvedValue({
      sent_as: 'text',
      rendered_text: 'here is the photo',
      attachments: null,
    });
    renderComposer({ mode: 'conversation', attachmentsEnabled: true, sendAdapter });
    await waitFor(() => expect(screen.getByTestId('composer-file-input')).toBeInTheDocument());

    attach(['photo.jpg']);
    fireEvent.change(screen.getByPlaceholderText('Type your message...'), {
      target: { value: 'here is the photo' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }));

    await waitFor(() => expect(sendAdapter).toHaveBeenCalled());
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('photo.jpg was not sent. Try again.'),
    );
    expect(screen.getByTestId('composer-attachments').textContent).toContain('photo.jpg');
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('a text-only send with no files staged is unaffected by the dropped-attachment guard', async () => {
    const sendAdapter = vi.fn().mockResolvedValue({
      sent_as: 'text',
      rendered_text: 'hello',
      attachments: null,
    });
    renderComposer({ mode: 'conversation', attachmentsEnabled: true, sendAdapter });
    await waitFor(() => expect(screen.getByTestId('composer-file-input')).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText('Type your message...'), {
      target: { value: 'hello' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }));

    await waitFor(() => expect(sendAdapter).toHaveBeenCalled());
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('FINDING 3: a thrown send keeps every file staged (nothing reached the contact)', async () => {
    const sendAdapter = vi.fn().mockRejectedValue(new Error('Network down'));
    renderComposer({ mode: 'conversation', attachmentsEnabled: true, sendAdapter });
    await waitFor(() => expect(screen.getByTestId('composer-file-input')).toBeInTheDocument());

    attach(['a.pdf', 'b.pdf']);
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Network down'));
    const staged = screen.getByTestId('composer-attachments').textContent ?? '';
    expect(staged).toContain('a.pdf');
    expect(staged).toContain('b.pdf');
  });

  it('freezes the staged files while a send is in flight', async () => {
    // The per-file outcome is POSITIONAL against the list the send carried, so
    // a removal accepted mid-flight is silently undone when the partial result
    // re-stages `sentFiles.slice(deliveredCount)` - the removed file comes back
    // and the next Send delivers it to the contact after all.
    let resolveSend: (v: unknown) => void = () => {};
    const sendAdapter = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSend = resolve;
        }),
    );
    renderComposer({ mode: 'conversation', attachmentsEnabled: true, sendAdapter });
    await waitFor(() => expect(screen.getByTestId('composer-file-input')).toBeInTheDocument());

    attach(['a.pdf', 'b.pdf', 'c.pdf']);
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }));
    await waitFor(() => expect(sendAdapter).toHaveBeenCalled());

    const removeC = screen.getByRole('button', { name: 'Remove c.pdf' });
    expect(removeC).toBeDisabled();
    // M6-01: Attach itself stays enabled through a send (only the per-file
    // remove is frozen, for the positional reason above) - `addFiles` already
    // no-ops while `sending` is true, so nothing actually gets staged either way.
    expect(screen.getByRole('button', { name: /attach/i })).not.toBeDisabled();

    fireEvent.click(removeC);
    expect(screen.getByTestId('composer-attachments').textContent).toContain('c.pdf');

    resolveSend({
      sent_as: 'attachment',
      attachments: {
        delivered: ['a.pdf'],
        failed: { filename: 'b.pdf', error: 'Respond 500 unavailable' },
      },
    });

    await waitFor(() => {
      const staged = screen.getByTestId('composer-attachments').textContent ?? '';
      expect(staged).not.toContain('a.pdf');
      expect(staged).toContain('b.pdf');
      expect(staged).toContain('c.pdf');
    });
    // Removal is available again once the send settles.
    expect(screen.getByRole('button', { name: 'Remove c.pdf' })).not.toBeDisabled();
  });

  // ------------------------------------------------- template send attribution

  it('FINDING 4: a manual template send carries the ticket id so the clock stops', async () => {
    (listApprovedTemplates as any).mockResolvedValue([
      {
        id: 'tpl-1',
        name: 'conversation_follow_up',
        language: 'en',
        param_count: 0,
        body_text: 'Hello from Sorento.',
        status: 'approved',
      },
    ]);
    (sendTemplateMessage as any).mockResolvedValue({ ok: true });

    renderComposer({
      entityType: 'conversation_sla',
      entityId: 'tracking-1',
      mode: 'conversation',
      templateSendTrackingId: 'tracking-1',
    });

    fireEvent.click(await screen.findByRole('button', { name: /send template/i }));
    fireEvent.click(await screen.findByTestId('template-option-conversation_follow_up'));
    // Dialog footer submit (the toolbar button shares the label).
    const submits = screen.getAllByRole('button', { name: /send template/i });
    fireEvent.click(submits[submits.length - 1]);

    await waitFor(() =>
      expect(sendTemplateMessage).toHaveBeenCalledWith(
        'conversation_sla',
        'tracking-1',
        expect.objectContaining({ template_id: 'tpl-1', tracking_id: 'tracking-1' }),
      ),
    );
  });

  it('other chat surfaces send no tracking id (unchanged behaviour)', async () => {
    (listApprovedTemplates as any).mockResolvedValue([
      {
        id: 'tpl-1',
        name: 'conversation_follow_up',
        language: 'en',
        param_count: 0,
        body_text: 'Hello from Sorento.',
        status: 'approved',
      },
    ]);
    (sendTemplateMessage as any).mockResolvedValue({ ok: true });

    renderComposer();

    fireEvent.click(await screen.findByRole('button', { name: /send template/i }));
    fireEvent.click(await screen.findByTestId('template-option-conversation_follow_up'));
    const submits = screen.getAllByRole('button', { name: /send template/i });
    fireEvent.click(submits[submits.length - 1]);

    await waitFor(() =>
      expect(sendTemplateMessage).toHaveBeenCalledWith(
        'complaint',
        'c1',
        expect.objectContaining({ tracking_id: null }),
      ),
    );
  });

  it('when !canReply, renders the not-available message and no composer', () => {
    renderComposer({ canReply: false, notAvailableMessage: 'No conversation linked here.' });
    expect(screen.getByText('No conversation linked here.')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Type your message...')).not.toBeInTheDocument();
    expect(screen.queryByTestId('composer-template-mode')).not.toBeInTheDocument();
  });
});
