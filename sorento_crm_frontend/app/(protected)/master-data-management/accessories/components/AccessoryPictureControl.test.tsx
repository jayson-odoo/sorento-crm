/**
 * PRICETAG-ACCESSORIES crew pass (6 Nov): picture upload, replace and remove on an accessory.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const hook = vi.hoisted(() => ({
  uploadMutateAsync: vi.fn(),
  deleteMutateAsync: vi.fn(),
  busy: false,
}));
vi.mock('../hooks/useAccessories', () => ({ useAccessoryImage: () => hook }));

import { AccessoryPictureControl } from './AccessoryPictureControl';

const base = { id: 'a1', name: 'COLANDER', spec: null, image: null, product_count: 0, combo_count: 0 };

describe('AccessoryPictureControl', () => {
  it('uploads the chosen file and hands the new picture up', async () => {
    const image = { attachment_id: 'att1', url: 'https://cdn.test/colander.jpg' };
    hook.uploadMutateAsync.mockResolvedValueOnce(image);
    const onChanged = vi.fn();
    render(<AccessoryPictureControl accessory={base as never} canEdit onChanged={onChanged} />);
    expect(screen.getByText('No picture')).toBeInTheDocument();
    const file = new File(['x'], 'colander.jpg', { type: 'image/jpeg' });
    fireEvent.change(screen.getByLabelText('COLANDER picture'), { target: { files: [file] } });
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(image));
    expect(hook.uploadMutateAsync).toHaveBeenCalledWith({ id: 'a1', file });
  });

  it('shows the picture with Replace and Remove, and Remove clears it', async () => {
    hook.deleteMutateAsync.mockResolvedValueOnce(undefined);
    const onChanged = vi.fn();
    const withImage = { ...base, image: { attachment_id: 'att1', url: 'https://cdn.test/c.jpg' } };
    const { container } = render(
      <AccessoryPictureControl accessory={withImage as never} canEdit onChanged={onChanged} />,
    );
    expect(container.querySelector('img')?.getAttribute('src')).toBe('https://cdn.test/c.jpg');
    expect(screen.getByRole('button', { name: /replace/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /remove/i }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(null));
    expect(hook.deleteMutateAsync).toHaveBeenCalledWith('a1');
  });

  it('read-only: no Upload, Replace or Remove', () => {
    render(<AccessoryPictureControl accessory={base as never} canEdit={false} onChanged={vi.fn()} />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});
