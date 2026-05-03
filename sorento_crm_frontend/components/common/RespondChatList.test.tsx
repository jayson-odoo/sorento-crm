import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import RespondChatList from './RespondChatList';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

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
