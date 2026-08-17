import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import RespondChatList from './RespondChatList';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

// The shared CRM preview surface is stubbed: what AC-D6 pins here is that an
// attachment bubble HANDS OFF to it (with the right item + start index), not
// the viewer's own rendering (covered by AttachmentPreviewModal.test.tsx).
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: ({
    open,
    items,
    startIndex,
  }: {
    open: boolean;
    items: Array<{ id: string; name: string; url: string }>;
    startIndex?: number;
  }) =>
    open ? (
      <div data-testid="attachment-preview" data-start-index={String(startIndex ?? 0)}>
        {items.map((it) => (
          <span key={it.id} data-url={it.url}>
            {it.name}
          </span>
        ))}
      </div>
    ) : null,
}));

const day1Ms = new Date('2026-02-02T10:24:00Z').getTime();
const day2Ms = new Date('2026-02-03T08:15:00Z').getTime();
const day3Ms = new Date('2026-02-04T09:00:00Z').getTime();

const items: RespondMessageRenderable[] = [
  {
    messageId: day1Ms * 1000,
    traffic: 'incoming',
    message: { type: 'text', text: 'thanks' },
    status: [],
    sender: { source: 'contact' },
  },
  {
    messageId: day1Ms * 1000 + 1,
    traffic: 'outgoing',
    message: {
      type: 'list',
      text: 'Welcome to Sorento CRM Support',
      list: {
        sections: [
          { rows: [{ title: 'General Enquiries' }, { title: 'Marketing Form' }] },
        ],
      },
    },
    status: [
      { value: 'sent', timestamp: day1Ms },
      { value: 'delivered', timestamp: day1Ms + 1000 },
      { value: 'read', timestamp: day1Ms + 2000 },
    ],
    sender: { source: 'workflow' },
  },
  {
    messageId: day2Ms * 1000,
    traffic: 'outgoing',
    message: { type: 'text', text: 'reply on day 2' },
    status: [{ value: 'delivered', timestamp: day2Ms }],
    sender: { source: 'n8n' },
  },
  {
    messageId: day3Ms * 1000,
    traffic: 'outgoing',
    message: { type: 'text', text: 'reply on day 3' },
    status: [{ value: 'sent', timestamp: day3Ms }],
    sender: { source: 'user' },
  },
];

// Our own outgoing upload: uuid SEGREGATES the key, the clean filename is the
// last segment (AC-D5), so both the bubble label and the preview title read it.
const XLSX_URL =
  'https://cdn.test/conversation_sla_tracking/biz-1/9f1c8f5e-aaaa-bbbb-cccc-1234567890ab/Q3_stock.xlsx';

const attachmentItems: RespondMessageRenderable[] = [
  {
    messageId: day1Ms * 1000,
    traffic: 'outgoing',
    message: { type: 'attachment', attachment: { type: 'file', url: XLSX_URL } },
    status: [{ value: 'sent', timestamp: day1Ms }],
    sender: { source: 'user' },
  },
];

const multiAttachmentItems: RespondMessageRenderable[] = [
  {
    messageId: day1Ms * 1000,
    traffic: 'incoming',
    message: {
      type: 'attachment',
      attachment: [
        { type: 'file', url: 'https://cdn.test/a/uuid/quote.pdf' },
        { type: 'image', url: 'https://cdn.test/a/uuid/site-photo.jpg' },
      ],
    },
    status: [],
    sender: { source: 'contact' },
  },
];

describe('RespondChatList — WhatsApp-style render', () => {
  it('renders contact name + phone in header', () => {
    render(
      <RespondChatList items={items} contactName="Jayson Teh" contactPhone="+60123456789" />,
    );
    expect(screen.getByText('Jayson Teh')).toBeDefined();
    expect(screen.getByText('+60123456789')).toBeDefined();
  });

  it('falls back to "Unknown contact" when no name', () => {
    render(<RespondChatList items={[]} />);
    expect(screen.getByText('Unknown contact')).toBeDefined();
    expect(screen.getByText('No messages yet.')).toBeDefined();
  });

  it('shows message text and selection options as a list', () => {
    render(<RespondChatList items={items} contactName="X" />);
    expect(screen.getByText('thanks')).toBeDefined();
    expect(screen.getByText('Welcome to Sorento CRM Support')).toBeDefined();
    expect(screen.getByText('General Enquiries')).toBeDefined();
    expect(screen.getByText('Marketing Form')).toBeDefined();
  });

  it('renders one date pill per distinct date (3 dates → 3 pills)', () => {
    const { container } = render(<RespondChatList items={items} contactName="X" />);
    const pills = container.querySelectorAll('div.sticky.top-0');
    expect(pills.length).toBe(3);
  });

  it('renders read receipt ticks: read tier shows sky-500 colored CheckCheck', () => {
    const { container } = render(<RespondChatList items={items} contactName="X" />);
    const readTick = container.querySelector('[aria-label="Read"]');
    const deliveredTick = container.querySelector('[aria-label="Delivered"]');
    const sentTick = container.querySelector('[aria-label="Sent"]');
    expect(readTick).not.toBeNull();
    expect(deliveredTick).not.toBeNull();
    expect(sentTick).not.toBeNull();
    expect(readTick?.getAttribute('class') || '').toMatch(/text-sky-500/);
  });

  it('an inbound message starting with ">" renders verbatim, no quote block', () => {
    const inboundQuoteLike: RespondMessageRenderable[] = [
      {
        messageId: 1,
        traffic: 'incoming',
        message: { type: 'text', text: '> is the promo price still valid?' },
        status: [],
        sender: { source: 'contact' },
      },
    ];
    const { container } = render(<RespondChatList items={inboundQuoteLike} contactName="X" />);
    expect(screen.getByText('> is the promo price still valid?')).toBeDefined();
    // The italic quote block is a bordered aside; inbound must never produce one.
    expect(container.querySelector('.border-emerald-500')).toBeNull();
    expect(screen.queryByText('(no text)')).toBeNull();
  });

  // The outbound ">"-prefix emulation was removed on 2026-08-16: Respond's send
  // API has no reply-to, so the block dressed ordinary text up as a real quote.
  // A historical message that carries a ">" line now renders it verbatim, which
  // is exactly what the contact received.
  it('an outgoing ">" line renders verbatim, with no quote block', () => {
    const outgoingQuoteLike: RespondMessageRenderable[] = [
      {
        messageId: 2,
        traffic: 'outgoing',
        message: { type: 'text', text: '> short by 2 boxes\nChecking now.' },
        status: [{ value: 'sent', timestamp: day1Ms }],
        sender: { source: 'user' },
      },
    ];
    const { container } = render(<RespondChatList items={outgoingQuoteLike} contactName="X" />);
    expect(screen.getByText('> short by 2 boxes Checking now.')).toBeDefined();
    expect(container.querySelector('.border-emerald-500')).toBeNull();
  });

  it('offers no per-bubble Reply affordance anywhere', () => {
    render(<RespondChatList items={items} contactName="X" />);
    expect(screen.queryByRole('button', { name: 'Reply to this message' })).toBeNull();
  });

  it('an attachment bubble shows the clean filename, never the uuid segment (AC-D5)', () => {
    render(<RespondChatList items={attachmentItems} contactName="X" />);
    expect(screen.getByText('Document · Q3_stock.xlsx')).toBeDefined();
    expect(screen.queryByText(/9f1c8f5e/)).toBeNull();
  });

  it('clicking an attachment bubble opens the shared preview surface (AC-D6)', () => {
    render(<RespondChatList items={attachmentItems} contactName="X" />);
    expect(screen.queryByTestId('attachment-preview')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Preview Q3_stock.xlsx' }));

    const preview = screen.getByTestId('attachment-preview');
    expect(preview.getAttribute('data-start-index')).toBe('0');
    expect(preview.querySelector('[data-url]')?.getAttribute('data-url')).toBe(XLSX_URL);
    expect(screen.getAllByText('Q3_stock.xlsx').length).toBeGreaterThan(0);
  });

  it('opens the preview at the clicked file when a message carries several', () => {
    render(<RespondChatList items={multiAttachmentItems} contactName="X" />);
    fireEvent.click(screen.getByRole('button', { name: 'Preview site-photo.jpg' }));
    const preview = screen.getByTestId('attachment-preview');
    expect(preview.getAttribute('data-start-index')).toBe('1');
    expect(preview.querySelectorAll('[data-url]')).toHaveLength(2);
  });

  it('an attachment with no url stays a static placeholder, not a button', () => {
    const noUrl: RespondMessageRenderable[] = [
      {
        messageId: 9,
        traffic: 'incoming',
        message: { type: 'sticker', attachment: { type: 'sticker' } },
        status: [],
        sender: { source: 'contact' },
      },
    ];
    render(<RespondChatList items={noUrl} contactName="X" />);
    expect(screen.getByText('Sticker')).toBeDefined();
    expect(screen.queryByRole('button', { name: /^Preview/ })).toBeNull();
  });

  it('uses WhatsApp background and bubble colors (only two bubble colors)', () => {
    const { container } = render(<RespondChatList items={items} contactName="X" />);
    const bg = container.querySelector('.bg-\\[\\#efeae2\\]');
    expect(bg).not.toBeNull();
    const incomingBubble = container.querySelector('.bg-white');
    const outgoingBubble = container.querySelector('.bg-\\[\\#d9fdd3\\]');
    expect(incomingBubble).not.toBeNull();
    expect(outgoingBubble).not.toBeNull();
  });
});
