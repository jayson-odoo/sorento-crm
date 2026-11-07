/**
 * SPEC-ICON-PICKER-UX (owner, 6 Nov): in select mode (`onDone`), a tile click toggles a visible
 * selected state instead of applying at once. Already-linked icons open selected, order is the
 * order of selection, Done hands back the ids, and Cancel / X / click-away discard. An upload joins
 * the grid already selected and still applies only on Done.
 *
 * Also: the designer's library filter narrows by KIND, the same field the spec picker uses, so the
 * two "Icons" lists are one list.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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
    { id: 'hot', name: 'Hot', kind: 'icon', tags: ['icon'], url: 'https://cdn.test/hot.png', mime_type: 'image/png' },
    { id: 'cold', name: 'Cold', kind: 'icon', tags: ['icon'], url: 'https://cdn.test/cold.png', mime_type: 'image/png' },
    { id: 'mixer', name: 'Mixer', kind: 'icon', tags: ['icon'], url: 'https://cdn.test/mixer.png', mime_type: 'image/png' },
  ]),
  uploadAsset: vi.fn(async () => ({
    id: 'steam',
    name: 'Steam',
    kind: 'icon',
    tags: ['icon'],
    url: 'https://cdn.test/steam.png',
    mime_type: 'image/png',
  })),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('../../services/assetService', () => ({ listAssets, uploadAsset }));
vi.mock('@/components/common/FileDropzone', () => ({
  FileDropzone: (props: { onFilesChange: (files: File[]) => void }) => (
    <button type="button" onClick={() => props.onFilesChange([new File(['x'], 'steam.png', { type: 'image/png' })])}>
      Choose file
    </button>
  ),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
  }) => (
    <select aria-label="Library filter" value={props.value} onChange={(e) => props.onChange(e.target.value)}>
      {props.options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { AssetPickerDialog } from './AssetPickerDialog';

function mount(selectedIds: string[] = ['cold']) {
  const onDone = vi.fn();
  const onCancel = vi.fn();
  const onPick = vi.fn();
  render(
    <AssetPickerDialog
      open
      productImages={[]}
      allowProductPhotos={false}
      libraryKind="icon"
      selectedIds={selectedIds}
      onDone={onDone}
      onCancel={onCancel}
      onPick={onPick}
    />,
  );
  return { onDone, onCancel, onPick };
}

const tile = (name: string) => screen.getByTitle(name);

beforeEach(() => {
  listAssets.mockClear();
  uploadAsset.mockClear();
});

describe('AssetPickerDialog select mode', () => {
  it('opens with the already-linked icons selected', async () => {
    mount(['cold']);
    await waitFor(() => expect(tile('Cold')).toBeInTheDocument());
    expect(tile('Cold')).toHaveAttribute('aria-pressed', 'true');
    expect(tile('Hot')).toHaveAttribute('aria-pressed', 'false');
  });

  it('a tile click toggles a visible selected state and applies nothing', async () => {
    const { onDone, onPick, onCancel } = mount([]);
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    fireEvent.click(tile('Hot'));
    expect(tile('Hot')).toHaveAttribute('aria-pressed', 'true');
    expect(tile('Hot').className).toMatch(/ring-primary/);
    fireEvent.click(tile('Hot'));
    expect(tile('Hot')).toHaveAttribute('aria-pressed', 'false');
    expect(onDone).not.toHaveBeenCalled();
    expect(onPick).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('Done hands back the selection in the order it was made, after the linked ones', async () => {
    const { onDone } = mount(['cold']);
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    fireEvent.click(tile('Mixer'));
    fireEvent.click(tile('Hot'));
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledWith(['cold', 'mixer', 'hot']);
  });

  it('Cancel discards the selection', async () => {
    const { onDone, onCancel } = mount(['cold']);
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    fireEvent.click(tile('Hot'));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
  });

  it('Escape (the X / click-away path) discards too', async () => {
    const { onDone, onCancel } = mount(['cold']);
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    fireEvent.click(tile('Hot'));
    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' });
    await waitFor(() => expect(onCancel).toHaveBeenCalled());
    expect(onDone).not.toHaveBeenCalled();
  });

  it('an upload joins the grid already selected, applied only on Done', async () => {
    const { onDone, onPick } = mount(['cold']);
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Choose file' }));
    fireEvent.click(screen.getByRole('button', { name: /^upload$/i }));
    await waitFor(() => expect(tile('Steam')).toBeInTheDocument());
    expect(uploadAsset).toHaveBeenCalledWith(expect.objectContaining({ kind: 'icon' }));
    expect(tile('Steam')).toHaveAttribute('aria-pressed', 'true');
    expect(onDone).not.toHaveBeenCalled();
    expect(onPick).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledWith(['cold', 'steam']);
  });
});

describe('AssetPickerDialog designer library: one library with the spec picker', () => {
  it('narrows by kind, the field the spec icon picker reads', async () => {
    render(
      <AssetPickerDialog open productImages={[]} allowProductPhotos={false} onCancel={vi.fn()} onPick={vi.fn()} />,
    );
    await waitFor(() => expect(listAssets).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText('Library filter'), { target: { value: 'icon' } });
    await waitFor(() => expect(listAssets).toHaveBeenLastCalledWith(expect.objectContaining({ kind: 'icon' })));
    expect(listAssets).not.toHaveBeenCalledWith(expect.objectContaining({ tag: 'icon' }));
  });
});
