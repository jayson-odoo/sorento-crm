/**
 * Quoted preview above the composer and the quoted send (#1317, AC-RT-13/14/17/19).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SharedConversationComposer from './SharedConversationComposer';

vi.mock('@/services/whatsappTemplateService', async () => {
  const actual = await vi.importActual<typeof import('@/services/whatsappTemplateService')>(
    '@/services/whatsappTemplateService',
  );
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

const REPLY_TO = { messageId: '1786000001000000', excerpt: 'Is the sink in stock?', senderLabel: 'Mr Loo' };

function renderComposer(props: Partial<React.ComponentProps<typeof SharedConversationComposer>> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const sendAdapter = vi.fn().mockResolvedValue({ sent_as: 'text' as const });
  const utils = render(
    <QueryClientProvider client={qc}>
      <SharedConversationComposer
        entityType="conversation_sla"
        entityId="t1"
        canReply
        mode="conversation"
        windowStateOverride={{ closed: false }}
        sendAdapter={sendAdapter}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { ...utils, sendAdapter };
}

function typeAndSend(text: string) {
  fireEvent.change(screen.getByPlaceholderText('Type your message...'), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
}

describe('SharedConversationComposer reply-to', () => {
  beforeEach(() => vi.clearAllMocks());

  it('AC-RT-13: shows the sender, the quoted text and a Cancel reply control', () => {
    renderComposer({ replyTo: REPLY_TO, onClearReplyTo: vi.fn() });
    const preview = screen.getByTestId('composer-reply-to');
    expect(preview).toHaveTextContent('Mr Loo');
    expect(preview).toHaveTextContent('Is the sink in stock?');
    expect(screen.getByRole('button', { name: 'Cancel reply' })).toBeInTheDocument();
  });

  it('AC-RT-13: the message box takes focus when a reply starts', async () => {
    const { rerender } = renderComposer();
    const qc = new QueryClient();
    rerender(
      <QueryClientProvider client={qc}>
        <SharedConversationComposer
          entityType="conversation_sla"
          entityId="t1"
          canReply
          mode="conversation"
          windowStateOverride={{ closed: false }}
          replyTo={REPLY_TO}
        />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByPlaceholderText('Type your message...')),
    );
  });

  it('AC-RT-14: Cancel reply asks the owner to drop the target', () => {
    const onClearReplyTo = vi.fn();
    renderComposer({ replyTo: REPLY_TO, onClearReplyTo });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel reply' }));
    expect(onClearReplyTo).toHaveBeenCalledTimes(1);
  });

  it('AC-RT-17: the send carries "> quote\\nbody" plus the audit fields, then clears the target', async () => {
    const onClearReplyTo = vi.fn();
    const { sendAdapter } = renderComposer({ replyTo: REPLY_TO, onClearReplyTo });
    typeAndSend('Yes, 3 units.');
    await waitFor(() => expect(sendAdapter).toHaveBeenCalledTimes(1));
    expect(sendAdapter.mock.calls[0][0]).toMatchObject({
      text: '> Is the sink in stock?\nYes, 3 units.',
      replyToMessageId: '1786000001000000',
      replyToExcerpt: 'Is the sink in stock?',
    });
    await waitFor(() => expect(onClearReplyTo).toHaveBeenCalled());
  });

  it('R2 (owner answer 2): a long quote goes out clipped at 160 characters with an ellipsis', async () => {
    const long = `${'word '.repeat(80)}END`;
    const { sendAdapter } = renderComposer({
      replyTo: { ...REPLY_TO, excerpt: long },
      onClearReplyTo: vi.fn(),
    });
    typeAndSend('Yes, 3 units.');
    await waitFor(() => expect(sendAdapter).toHaveBeenCalledTimes(1));
    const [quoteLine, answer] = (sendAdapter.mock.calls[0][0].text as string).split('\n');
    expect(quoteLine.startsWith('> ')).toBe(true);
    expect(quoteLine.endsWith('…')).toBe(true);
    expect(quoteLine.length).toBeLessThanOrEqual(2 + 160 + 1);
    expect(quoteLine).not.toContain('END');
    expect(answer).toBe('Yes, 3 units.');
  });

  it('AC-RT-17: the post-send clear names the target it sent, so a newer pick survives', async () => {
    const onClearReplyTo = vi.fn();
    const { sendAdapter } = renderComposer({ replyTo: REPLY_TO, onClearReplyTo });
    typeAndSend('Yes');
    await waitFor(() => expect(sendAdapter).toHaveBeenCalled());
    await waitFor(() => expect(onClearReplyTo).toHaveBeenCalledWith(REPLY_TO));
  });

  it('AC-RT-17: outside the 24h window the quote still goes, with the one-line warning', () => {
    renderComposer({
      replyTo: REPLY_TO,
      onClearReplyTo: vi.fn(),
      windowStateOverride: {
        closed: true,
        template: {
          configured: true,
          template_name: 'chat_reply',
          body_text: 'Hi, {{1}}',
          slots: { '1': { editable: true } },
        } as never,
      },
    });
    expect(screen.getByTestId('composer-reply-to')).toBeInTheDocument();
    expect(screen.getByTestId('flatten-warning')).toBeInTheDocument();
  });

  it('AC-RT-17: a failed send keeps the target so a retry still quotes', async () => {
    const onClearReplyTo = vi.fn();
    const sendAdapter = vi.fn().mockRejectedValue(new Error('boom'));
    renderComposer({ replyTo: REPLY_TO, onClearReplyTo, sendAdapter });
    typeAndSend('Yes');
    await waitFor(() => expect(sendAdapter).toHaveBeenCalled());
    expect(onClearReplyTo).not.toHaveBeenCalled();
  });

  it('AC-RT-19: without a target the text goes as typed with no reply fields', async () => {
    const { sendAdapter } = renderComposer();
    expect(screen.queryByTestId('composer-reply-to')).toBeNull();
    typeAndSend('plain answer');
    await waitFor(() => expect(sendAdapter).toHaveBeenCalledTimes(1));
    const payload = sendAdapter.mock.calls[0][0];
    expect(payload.text).toBe('plain answer');
    expect(payload.replyToMessageId ?? null).toBeNull();
    expect(payload.replyToExcerpt ?? null).toBeNull();
  });
});
