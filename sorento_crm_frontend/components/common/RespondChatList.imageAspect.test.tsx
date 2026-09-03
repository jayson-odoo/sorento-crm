import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import RespondChatList from './RespondChatList';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

/**
 * M6-07: a chat image sits in a fixed aspect-[4/3] box, not a natural-size
 * <img> with zero height until it loads. A thread pinned to its tail (the
 * ordinary case) would otherwise have to re-settle as each photo finishes
 * loading; the reserved box means the scroll position it already computed
 * stays correct.
 */
const imageItem: RespondMessageRenderable = {
  messageId: 1,
  traffic: 'incoming',
  message: {
    type: 'attachment',
    attachment: { type: 'image', url: 'https://cdn.test/a/uuid/site-photo.jpg' },
  },
};

describe('chat image aspect box (M6-07)', () => {
  it('wraps the image in a fixed aspect-[4/3] box with object-contain', () => {
    render(<RespondChatList items={[imageItem]} />);
    const img = screen.getByRole('img') as HTMLImageElement;
    expect(img.className).toContain('object-contain');
    const box = img.parentElement;
    expect(box?.className).toContain('aspect-[4/3]');
  });
});
