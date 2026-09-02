/**
 * Pasting into the composer (feedback 2026-08-16, item 3).
 *
 * WhatsApp / Respond let you paste a screenshot straight into the message box.
 * Here that must go through the SAME staging path as the Attach button (one
 * send carrying text + files), show a thumbnail rather than an unreadable
 * "image.png", and open the SHARED attachment preview when the thumbnail is
 * clicked. No captions: Respond.io has none either.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import SharedConversationComposer from './SharedConversationComposer';

vi.mock('@/services/whatsappTemplateService', async () => {
  const actual = await vi.importActual<
    typeof import('@/services/whatsappTemplateService')
  >('@/services/whatsappTemplateService');
  return {
    ...actual,
    getWindowState: vi.fn().mockResolvedValue({
      open: true,
      last_incoming_at: null,
      checked_at: '2026-08-16T00:00:00Z',
    }),
    sendConversationMessage: vi.fn(),
    getChatTemplatePreview: vi.fn(),
    listApprovedTemplates: vi.fn().mockResolvedValue([]),
    sendTemplateMessage: vi.fn(),
  };
});

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

/** The shared preview surface, stubbed to a marker: what matters here is that
 *  the composer routes a staged image to THAT component, with that item. */
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: ({
    open,
    items,
    startIndex,
  }: {
    open: boolean;
    items: { id: string; name: string; url: string }[];
    startIndex?: number;
  }) =>
    open ? (
      <div
        data-testid="attachment-preview"
        data-names={items.map((i) => i.name).join(',')}
        data-urls={items.map((i) => i.url).join(',')}
        data-start={String(startIndex ?? 0)}
      />
    ) : null,
}));

// jsdom implements neither of these.
const createdUrls: string[] = [];
const revokedUrls: string[] = [];
beforeEach(() => {
  createdUrls.length = 0;
  revokedUrls.length = 0;
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    writable: true,
    value: (file: File) => {
      const url = `blob:staged/${file.name}`;
      createdUrls.push(url);
      return url;
    },
  });
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    writable: true,
    value: (url: string) => revokedUrls.push(url),
  });
});

function renderComposer(
  props: Partial<React.ComponentProps<typeof SharedConversationComposer>> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const sendAdapter = vi.fn().mockResolvedValue({
    sent_as: 'attachment',
    attachments: { delivered: ['shot.png'], failed: null },
  });
  render(
    <QueryClientProvider client={qc}>
      <SharedConversationComposer
        entityType="conversation_sla"
        entityId="t1"
        canReply
        mode="conversation"
        attachmentsEnabled
        sendAdapter={sendAdapter}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { sendAdapter };
}

function pasteFiles(files: File[]) {
  const textarea = screen.getByPlaceholderText('Type your message...');
  fireEvent.paste(textarea, { clipboardData: { files } });
  return textarea;
}

const image = (name = 'shot.png') => new File(['x'], name, { type: 'image/png' });

describe('SharedConversationComposer paste-to-attach', () => {
  it('stages a pasted image as an attachment, with a thumbnail and a remove control', async () => {
    renderComposer();
    await screen.findByTestId('composer-file-input');

    pasteFiles([image()]);

    const staged = await screen.findByTestId('composer-attachment');
    expect(staged).toHaveTextContent('shot.png');
    expect(screen.getByAltText('shot.png')).toHaveAttribute('src', 'blob:staged/shot.png');
    expect(screen.getByRole('button', { name: 'Remove shot.png' })).toBeInTheDocument();
  });

  it('stages a pasted NON-image the same way, as a named chip', async () => {
    renderComposer();
    await screen.findByTestId('composer-file-input');

    pasteFiles([new File(['x'], 'quote.pdf', { type: 'application/pdf' })]);

    expect(await screen.findByTestId('composer-attachment')).toHaveTextContent('quote.pdf');
    expect(screen.queryByAltText('quote.pdf')).not.toBeInTheDocument();
  });

  it('a text-only paste stages nothing and is left to the browser', async () => {
    renderComposer();
    const textarea = await screen.findByPlaceholderText('Type your message...');

    const event = new Event('paste', { bubbles: true, cancelable: true });
    Object.defineProperty(event, 'clipboardData', { value: { files: [] } });
    textarea.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(false);
    expect(screen.queryByTestId('composer-attachments')).not.toBeInTheDocument();
  });

  it('does nothing on a surface that cannot send attachments', async () => {
    renderComposer({ attachmentsEnabled: false, sendAdapter: undefined });
    await screen.findByPlaceholderText('Type your message...');

    pasteFiles([image()]);

    expect(screen.queryByTestId('composer-attachments')).not.toBeInTheDocument();
  });

  it('clicking the thumbnail opens the shared attachment preview on that file', async () => {
    renderComposer();
    await screen.findByTestId('composer-file-input');
    pasteFiles([image('one.png'), image('two.png')]);
    await screen.findByAltText('two.png');

    fireEvent.click(screen.getByRole('button', { name: 'Preview two.png' }));

    const preview = screen.getByTestId('attachment-preview');
    expect(preview).toHaveAttribute('data-names', 'one.png,two.png');
    expect(preview).toHaveAttribute('data-urls', 'blob:staged/one.png,blob:staged/two.png');
    expect(preview).toHaveAttribute('data-start', '1');
  });

  it('removing a staged image drops it and revokes its object URL', async () => {
    renderComposer();
    await screen.findByTestId('composer-file-input');
    pasteFiles([image()]);
    await screen.findByAltText('shot.png');

    fireEvent.click(screen.getByRole('button', { name: 'Remove shot.png' }));

    await waitFor(() =>
      expect(screen.queryByTestId('composer-attachments')).not.toBeInTheDocument(),
    );
    expect(revokedUrls).toContain('blob:staged/shot.png');
  });

  it('sends the typed text and the pasted image in ONE send', async () => {
    const { sendAdapter } = renderComposer();
    await screen.findByTestId('composer-file-input');
    const textarea = pasteFiles([image()]);
    fireEvent.change(textarea, { target: { value: 'here is the leak' } });

    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }));

    await waitFor(() => expect(sendAdapter).toHaveBeenCalledTimes(1));
    const payload = sendAdapter.mock.calls[0][0] as { text: string; files: File[] };
    expect(payload.text).toBe('here is the leak');
    expect(payload.files.map((f) => f.name)).toEqual(['shot.png']);
  });
});
