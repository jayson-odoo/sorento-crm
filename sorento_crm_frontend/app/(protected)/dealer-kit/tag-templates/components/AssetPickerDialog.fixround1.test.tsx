/**
 * Feature icons review fix round 1 (B2): opened to manage ONE kind (the icon library from a
 * Feature icons layer or the spec screen), the picker lists only that kind, files an upload as it,
 * and keeps the new asset in the list instead of picking it. Owner ruling 5 Nov 20:35: the rule
 * lives on the spec value, so no asset offers "Show when" any more.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
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

const { listAssets, uploadAsset } = vi.hoisted(() => ({
  listAssets: vi.fn(async () => [
    { id: 'icon1', name: 'Hot', kind: 'icon', tags: [], url: 'https://cdn.test/hot.png', mime_type: 'image/png' },
  ]),
  uploadAsset: vi.fn(async () => ({
    id: 'icon2',
    name: 'Cold',
    kind: 'icon',
    tags: [],
    url: 'https://cdn.test/cold.png',
    mime_type: 'image/png',
  })),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../services/assetService', () => ({ listAssets, uploadAsset }));
vi.mock('@/components/common/FileDropzone', () => ({
  FileDropzone: (props: { onFilesChange: (files: File[]) => void }) => (
    <button type="button" onClick={() => props.onFilesChange([new File(['x'], 'cold.png', { type: 'image/png' })])}>
      Choose file
    </button>
  ),
}));

import { AssetPickerDialog } from './AssetPickerDialog';

function mount(onPick = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AssetPickerDialog
        open
        productImages={[]}
        allowProductPhotos={false}
        libraryKind="icon"
        onCancel={vi.fn()}
        onPick={onPick}
      />
    </QueryClientProvider>,
  );
  return onPick;
}

describe('AssetPickerDialog managing the icon library', () => {
  it('lists only icons', async () => {
    mount();
    await waitFor(() => expect(screen.getByTitle('Hot')).toBeInTheDocument());
    expect(listAssets).toHaveBeenCalledWith(expect.objectContaining({ kind: 'icon' }));
  });

  it('files an upload as an icon and keeps it in the list instead of picking it', async () => {
    const onPick = mount();
    await waitFor(() => expect(screen.getByTitle('Hot')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Choose file' }));
    fireEvent.click(screen.getByRole('button', { name: /upload/i }));
    await waitFor(() => expect(uploadAsset).toHaveBeenCalled());
    expect(uploadAsset).toHaveBeenCalledWith(expect.objectContaining({ kind: 'icon' }));
    await waitFor(() => expect(screen.getByTitle('Cold')).toBeInTheDocument());
    expect(onPick).not.toHaveBeenCalled();
  });

  it('offers no "Show when" on any icon', async () => {
    mount();
    await waitFor(() => expect(screen.getByTitle('Hot')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /show when/i })).toBeNull();
  });
});
