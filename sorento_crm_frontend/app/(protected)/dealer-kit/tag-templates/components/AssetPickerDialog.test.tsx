/**
 * The library grid draws a rendition per asset (`thumb_url`), never up to 200 originals. An older
 * reply without `thumb_url` still draws `url`.
 */
import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
if (!(globalThis as { ResizeObserver?: unknown }).ResizeObserver) {
  (globalThis as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => [
    {
      id: 'a1',
      name: 'Logo',
      kind: 'logo',
      tags: [],
      url: 'https://cdn.test/original-7mb.png',
      thumb_url: 'https://cdn.test/logo.thumb.jpg',
      mime_type: 'image/png',
    },
    {
      id: 'a2',
      name: 'Old reply',
      kind: 'icon',
      tags: [],
      url: 'https://cdn.test/old.png',
      mime_type: 'image/png',
    },
  ]),
  uploadAsset: vi.fn(),
}));

import { AssetPickerDialog } from './AssetPickerDialog';

describe('AssetPickerDialog grid', () => {
  it('draws the thumb_url, and falls back to url only when there is none', async () => {
    render(
      <AssetPickerDialog
        open
        productImages={[]}
        allowProductPhotos={false}
        onCancel={vi.fn()}
        onPick={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByTitle('Logo')).toBeInTheDocument());
    const logo = screen.getByTitle('Logo').querySelector('img');
    expect(logo).toHaveAttribute('src', 'https://cdn.test/logo.thumb.jpg');
    const old = screen.getByTitle('Old reply').querySelector('img');
    expect(old).toHaveAttribute('src', 'https://cdn.test/old.png');
  });
});
