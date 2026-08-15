import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import RespondChatList from './RespondChatList';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

/**
 * UAC AC-N4: chat media lives on hosts that send no CORS headers, so an .xlsx
 * bubble used to dead-end on "No source available to load this file". What is
 * pinned here is the WIRING: with a `mediaProxy` the preview item gains a byte
 * source and the modal's `fetchBytes` routes through the proxy; without one the
 * surface behaves exactly as it did (portal thread, complaint / SI / PR panels).
 */
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: ({
    open,
    items,
    fetchBytes,
  }: {
    open: boolean;
    items: Array<{ id: string; name: string; url: string; downloadUrl?: string }>;
    fetchBytes?: (item: { id: string; name: string; url: string; downloadUrl?: string }) => Promise<Response>;
  }) =>
    open ? (
      <div data-testid="attachment-preview" data-has-fetch-bytes={fetchBytes ? 'yes' : 'no'}>
        {items.map((it) => (
          <button
            key={it.id}
            type="button"
            data-testid={`preview-item-${it.name}`}
            data-download-url={it.downloadUrl ?? ''}
            onClick={() => void fetchBytes?.(it)}
          >
            {it.name}
          </button>
        ))}
      </div>
    ) : null,
}));

const sentMs = new Date('2026-02-02T10:24:00Z').getTime();

const XLSX_URL = 'https://cdn.test/conversation_sla_tracking/biz-1/uuid/Q3_stock.xlsx';

const attachmentItems: RespondMessageRenderable[] = [
  {
    messageId: sentMs * 1000,
    traffic: 'outgoing',
    message: { type: 'attachment', attachment: { type: 'file', url: XLSX_URL } },
    status: [{ value: 'sent', timestamp: sentMs }],
    sender: { source: 'user' },
  },
];

function openPreview() {
  fireEvent.click(screen.getByRole('button', { name: 'Preview Q3_stock.xlsx' }));
  return screen.getByTestId('attachment-preview');
}

describe('RespondChatList chat-media proxy (AC-N4)', () => {
  it('without a mediaProxy the preview item carries no byte source (unchanged)', () => {
    render(<RespondChatList items={attachmentItems} contactName="X" />);
    const preview = openPreview();
    expect(preview.getAttribute('data-has-fetch-bytes')).toBe('no');
    expect(screen.getByTestId('preview-item-Q3_stock.xlsx').getAttribute('data-download-url')).toBe(
      '',
    );
  });

  it('with a mediaProxy the item gains a byte source and fetchBytes is supplied', () => {
    const mediaProxy = vi.fn(async () => new Response());
    render(<RespondChatList items={attachmentItems} contactName="X" mediaProxy={mediaProxy} />);
    const preview = openPreview();
    expect(preview.getAttribute('data-has-fetch-bytes')).toBe('yes');
    expect(screen.getByTestId('preview-item-Q3_stock.xlsx').getAttribute('data-download-url')).toBe(
      XLSX_URL,
    );
  });

  it('fetchBytes routes the attachment url through the proxy (Excel + Download)', () => {
    const mediaProxy = vi.fn(async () => new Response());
    render(<RespondChatList items={attachmentItems} contactName="X" mediaProxy={mediaProxy} />);
    openPreview();

    fireEvent.click(screen.getByTestId('preview-item-Q3_stock.xlsx'));

    expect(mediaProxy).toHaveBeenCalledTimes(1);
    expect(mediaProxy).toHaveBeenCalledWith(XLSX_URL);
  });

  it('an image bubble still renders straight from the CDN url', () => {
    const imageItems: RespondMessageRenderable[] = [
      {
        messageId: 11,
        traffic: 'incoming',
        message: {
          type: 'attachment',
          attachment: { type: 'image', url: 'https://cdn.test/a/uuid/site-photo.jpg' },
        },
        status: [],
        sender: { source: 'contact' },
      },
    ];
    const { container } = render(
      <RespondChatList items={imageItems} contactName="X" mediaProxy={async () => new Response()} />,
    );
    expect(container.querySelector('img')?.getAttribute('src')).toBe(
      'https://cdn.test/a/uuid/site-photo.jpg',
    );
  });
});
