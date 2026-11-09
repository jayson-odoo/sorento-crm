/**
 * Two overlapping picture removals: each picture leaves the list when ITS removal commits (the list is read
 * back from the server), never the wrong one, and a cancelled one stays.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

const hooks = vi.hoisted(() => ({
  run: vi.fn(),
  committed: { current: undefined as undefined | (() => void) },
  fresh: vi.fn(),
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({ useRowPending: () => () => false }));
vi.mock('../hooks/useAccessories', () => ({
  useAccessoryPictures: () => ({
    addMutateAsync: vi.fn(),
    patchMutateAsync: vi.fn(),
    orderMutateAsync: vi.fn(),
    busy: false,
  }),
  useDeleteAccessoryPicture: (onCommitted: () => void) => {
    hooks.committed.current = onCommitted;
    return { run: hooks.run };
  },
  useFreshAccessoryPictures: () => hooks.fresh,
}));

import { AccessoryPicturesField } from './AccessoryPicturesField';
import type { AccessoryPicture } from '../types/accessory.types';

const pic = (id: string, name: string) => ({
  id, attachment_id: `att-${id}`, url: `https://cdn.test/${id}.jpg`, colour_name: name, colour_hex: null,
});
const A = pic('i1', 'Black');
const B = pic('i2', 'Grey');
const C = pic('i3', 'Gold');

function Harness() {
  const [pictures, setPictures] = useState<AccessoryPicture[]>([A, B, C]);
  return <AccessoryPicturesField accessoryId="a1" pictures={pictures} canEdit onChanged={setPictures} />;
}

describe('AccessoryPicturesField removals', () => {
  it('drops the picture whose removal committed, even with two countdowns running', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', { name: 'Remove picture 1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove picture 2' }));
    expect(hooks.run).toHaveBeenNthCalledWith(1, expect.objectContaining({ id: 'i1' }));
    expect(hooks.run).toHaveBeenNthCalledWith(2, expect.objectContaining({ id: 'i2' }));

    // The first countdown lapses: only the first picture is gone on the server.
    hooks.fresh.mockResolvedValueOnce([B, C]);
    hooks.committed.current?.();
    await waitFor(() => expect(document.querySelectorAll('img')).toHaveLength(2));
    expect(document.querySelector('img[src$="i1.jpg"]')).toBeNull();
    expect(document.querySelector('img[src$="i2.jpg"]')).not.toBeNull();

    // The second one is cancelled elsewhere and a later commit reads back the server: Grey stays.
    hooks.fresh.mockResolvedValueOnce([B, C]);
    hooks.committed.current?.();
    await waitFor(() => expect(hooks.fresh).toHaveBeenCalledTimes(2));
    expect(document.querySelector('img[src$="i2.jpg"]')).not.toBeNull();
  });
});
