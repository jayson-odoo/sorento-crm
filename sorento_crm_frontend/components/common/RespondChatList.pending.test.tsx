import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import RespondChatList from './RespondChatList';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

/**
 * M6-01: the optimistic bubble a composer stages via `usePendingThreadItems`
 * is the same `RespondMessageRenderable` shape as a real message, marked only
 * by `source: 'pending'` - this is the one place that dims it, so every
 * consumer (drawer, inbox, or a plain entity chat panel) inherits the same
 * visual without re-deciding it per screen.
 */
function pendingItem(text: string): RespondMessageRenderable {
  return {
    traffic: 'outgoing',
    message: { type: 'text', text },
    status: [{ value: 'pending', timestamp: Date.now() }],
    source: 'pending',
    pendingKey: 'pending-1',
  } as RespondMessageRenderable;
}

describe('pending (optimistic) bubbles', () => {
  it('dims a pending bubble with opacity-60', () => {
    render(<RespondChatList items={[pendingItem('on my way')]} />);
    const bubble = screen.getByText('on my way').closest('div[class*="rounded-lg"]');
    expect(bubble).not.toBeNull();
    expect(bubble?.className).toContain('opacity-60');
  });

  it('a real (non-pending) bubble is never dimmed', () => {
    render(
      <RespondChatList
        items={[
          {
            messageId: 1,
            traffic: 'outgoing',
            message: { type: 'text', text: 'delivered already' },
          },
        ]}
      />,
    );
    const bubble = screen.getByText('delivered already').closest('div[class*="rounded-lg"]');
    expect(bubble?.className).not.toContain('opacity-60');
  });
});
