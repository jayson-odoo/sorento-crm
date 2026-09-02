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

import { getWindowState, sendConversationMessage } from '@/services/whatsappTemplateService';
import { toast } from '@/lib/toast';

if (!(Element.prototype as any).scrollIntoView) {
  (Element.prototype as any).scrollIntoView = vi.fn();
}

function renderComposer(
  props: Partial<React.ComponentProps<typeof SharedConversationComposer>> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SharedConversationComposer entityType="complaint" entityId="c1" canReply {...props} />
    </QueryClientProvider>,
  );
}

const OPEN = { open: true, last_incoming_at: null, checked_at: '2026-07-01T00:00:00Z' };

describe('SharedConversationComposer - optimistic send (M6-01)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (getWindowState as any).mockResolvedValue(OPEN);
  });

  it('never disables the textarea while sending; focus and caret survive the send', async () => {
    let resolveSend: (v: unknown) => void = () => {};
    (sendConversationMessage as any).mockImplementation(
      () => new Promise((resolve) => { resolveSend = resolve; }),
    );
    renderComposer();
    await waitFor(() => expect(getWindowState).toHaveBeenCalled());

    const textarea = screen.getByPlaceholderText(
      'Type your message...',
    ) as HTMLTextAreaElement;
    textarea.focus();
    fireEvent.change(textarea, { target: { value: 'hello there' } });
    expect(document.activeElement).toBe(textarea);

    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(sendConversationMessage).toHaveBeenCalled());

    // In flight: never disabled.
    expect(textarea).not.toBeDisabled();
    // The Send button IS disabled while sending - the guard is the button, not the field.
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();

    resolveSend({ sent_as: 'text' });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());

    // Refocused after the send settles (the queueMicrotask pattern at :195).
    await waitFor(() => expect(document.activeElement).toBe(textarea));
    expect(textarea).not.toBeDisabled();
    // Sending flipped back false - the field accepts the next message and the
    // Send button re-arms once there is something to send again.
    fireEvent.change(textarea, { target: { value: 'next message' } });
    expect(screen.getByRole('button', { name: 'Send' })).not.toBeDisabled();
  });

  it('a second Enter while sending is ignored (re-entry guard)', async () => {
    let resolveSend: (v: unknown) => void = () => {};
    (sendConversationMessage as any).mockImplementation(
      () => new Promise((resolve) => { resolveSend = resolve; }),
    );
    renderComposer();
    await waitFor(() => expect(getWindowState).toHaveBeenCalled());

    const textarea = screen.getByPlaceholderText('Type your message...');
    fireEvent.change(textarea, { target: { value: 'one' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
    await waitFor(() => expect(sendConversationMessage).toHaveBeenCalledTimes(1));

    // The field is not disabled, so typing and pressing Enter again is possible -
    // it must still be a no-op while the first send is in flight.
    fireEvent.change(textarea, { target: { value: 'one more' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    resolveSend({ sent_as: 'text' });
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(sendConversationMessage).toHaveBeenCalledTimes(1);
  });

  it('shows an optimistic bubble immediately and clears it once the send settles', async () => {
    let resolveSend: (v: unknown) => void = () => {};
    (sendConversationMessage as any).mockImplementation(
      () => new Promise((resolve) => { resolveSend = resolve; }),
    );
    const add = vi.fn().mockReturnValue('pending-1');
    const remove = vi.fn();
    renderComposer({ pendingBubble: { add, remove } });
    await waitFor(() => expect(getWindowState).toHaveBeenCalled());

    const textarea = screen.getByPlaceholderText('Type your message...');
    fireEvent.change(textarea, { target: { value: 'on my way' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    // Added before the request settles.
    await waitFor(() => expect(add).toHaveBeenCalledWith({ text: 'on my way', files: [] }));
    expect(remove).not.toHaveBeenCalled();

    resolveSend({ sent_as: 'text' });
    await waitFor(() => expect(remove).toHaveBeenCalledWith('pending-1'));
  });

  it('removes the bubble and toasts on failure', async () => {
    (sendConversationMessage as any).mockRejectedValue(new Error('Network down'));
    const add = vi.fn().mockReturnValue('pending-2');
    const remove = vi.fn();
    renderComposer({ pendingBubble: { add, remove } });
    await waitFor(() => expect(getWindowState).toHaveBeenCalled());

    fireEvent.change(screen.getByPlaceholderText('Type your message...'), {
      target: { value: 'hello' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(remove).toHaveBeenCalledWith('pending-2'));
    expect(toast.error).toHaveBeenCalledWith('Network down');
  });

  it('waits for an async onSent to settle before clearing the bubble', async () => {
    (sendConversationMessage as any).mockResolvedValue({ sent_as: 'text' });
    const add = vi.fn().mockReturnValue('pending-3');
    const remove = vi.fn();
    let resolveOnSent: () => void = () => {};
    const onSent = vi.fn().mockImplementation(
      () => new Promise<void>((resolve) => { resolveOnSent = resolve; }),
    );
    renderComposer({ pendingBubble: { add, remove }, onSent });
    await waitFor(() => expect(getWindowState).toHaveBeenCalled());

    fireEvent.change(screen.getByPlaceholderText('Type your message...'), {
      target: { value: 'hello' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(onSent).toHaveBeenCalled());
    // The refetch onSent triggered has not resolved yet - the bubble stays so
    // the real row and the placeholder are never both missing at once.
    expect(remove).not.toHaveBeenCalled();

    resolveOnSent();
    await waitFor(() => expect(remove).toHaveBeenCalledWith('pending-3'));
  });
});
