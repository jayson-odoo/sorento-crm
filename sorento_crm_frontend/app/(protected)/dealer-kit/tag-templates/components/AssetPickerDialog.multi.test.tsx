/**
 * PRICETAG-DESIGNER-FEEDBACK B1, AC-6.1 and AC-6.2: pick and upload several images.
 *
 * AC-6.1 the upload drop zone takes several files at once (same types, 20 MB each); each is
 * uploaded with the existing `uploadAsset`, one call per file, in order, and all join the
 * library. A file over the limit or of a wrong type is named in a notice; the others still upload.
 * AC-6.2 optional `onPickMany(sources)`: tiles toggle, the footer says "N selected", one Done
 * hands back the picked sources in pick order, and uploads in this mode join the selection.
 * Without it, pick mode is unchanged.
 *
 * The REAL `FileDropzone` is used (its hidden input, labelled by the zone's title "Upload
 * artwork", is fed the files), so the per-file type / size rules are the shared ones. Written
 * test-FIRST.
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

const { listAssets, uploadAsset, toast } = vi.hoisted(() => ({
  listAssets: vi.fn(async () => [
    { id: 'hot', name: 'Hot', kind: 'icon', tags: ['icon'], url: 'https://cdn.test/hot.png', mime_type: 'image/png' },
    { id: 'cold', name: 'Cold', kind: 'icon', tags: ['icon'], url: 'https://cdn.test/cold.png', mime_type: 'image/png' },
    { id: 'mixer', name: 'Mixer', kind: 'icon', tags: ['icon'], url: 'https://cdn.test/mixer.png', mime_type: 'image/png' },
  ]),
  // The new asset is named after its file ("alpha.png" -> id "alpha", name "Alpha").
  uploadAsset: vi.fn(async ({ file, kind }: { file: File; kind: string }) => {
    const id = file.name.replace(/\.[^.]+$/, '');
    return {
      id,
      name: id[0].toUpperCase() + id.slice(1),
      kind,
      tags: [kind],
      url: `https://cdn.test/${file.name}`,
      mime_type: file.type,
    };
  }),
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), message: vi.fn() },
}));

vi.mock('@/lib/toast', () => ({ toast }));
vi.mock('../../services/assetService', () => ({ listAssets, uploadAsset }));
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

const MB = 1024 * 1024;

function file(name: string, type = 'image/png', size?: number): File {
  const out = new File(['x'], name, { type });
  if (size !== undefined) Object.defineProperty(out, 'size', { value: size });
  return out;
}

function drop(files: File[]) {
  const input = screen.getByLabelText('Upload artwork') as HTMLInputElement;
  fireEvent.change(input, { target: { files } });
}

const tile = (name: string) => screen.getByTitle(name);
const uploadButton = () => screen.getByRole('button', { name: /^upload$/i });
const uploadedNames = () => uploadAsset.mock.calls.map((call) => (call[0] as { file: File }).file.name);

/** Every text a notice could carry: the dialog's own text and every toast call. */
function noticeText(): string {
  const toasts = Object.values(toast)
    .flatMap((fn) => fn.mock.calls)
    .map((call) => call.map((arg: unknown) => (typeof arg === 'string' ? arg : JSON.stringify(arg))).join(' '));
  return [document.body.textContent ?? '', ...toasts].join('\n');
}

beforeEach(() => {
  listAssets.mockClear();
  uploadAsset.mockClear();
  Object.values(toast).forEach((fn) => fn.mockClear());
});

function mountLibrary() {
  const onPick = vi.fn();
  render(
    <AssetPickerDialog
      open
      productImages={[]}
      allowProductPhotos={false}
      libraryKind="icon"
      onCancel={vi.fn()}
      onPick={onPick}
    />,
  );
  return { onPick };
}

function mountMany(productImages: { attachment_id: string; url: string; is_primary: boolean }[] = []) {
  const onPickMany = vi.fn();
  const onPick = vi.fn();
  const onCancel = vi.fn();
  const props = { onPickMany } as Record<string, unknown>;
  render(
    <AssetPickerDialog
      open
      productImages={productImages}
      allowProductPhotos={productImages.length > 0}
      onCancel={onCancel}
      onPick={onPick}
      {...props}
    />,
  );
  return { onPickMany, onPick, onCancel };
}

describe('AssetPickerDialog: several files at once (AC-6.1)', () => {
  it('the drop zone takes several files', async () => {
    mountLibrary();
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    expect((screen.getByLabelText('Upload artwork') as HTMLInputElement).multiple).toBe(true);
  });

  it('uploads each file with uploadAsset, one call per file, in order, and all join the library', async () => {
    mountLibrary();
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    drop([file('alpha.png'), file('beta.svg', 'image/svg+xml'), file('gamma.webp', 'image/webp')]);
    fireEvent.click(uploadButton());

    await waitFor(() => expect(uploadAsset).toHaveBeenCalledTimes(3));
    expect(uploadedNames()).toEqual(['alpha.png', 'beta.svg', 'gamma.webp']);
    for (const call of uploadAsset.mock.calls) {
      expect(call[0]).toEqual(expect.objectContaining({ kind: 'icon' }));
    }
    await waitFor(() => expect(tile('Gamma')).toBeInTheDocument());
    expect(tile('Alpha')).toBeInTheDocument();
    expect(tile('Beta')).toBeInTheDocument();
    expect(tile('Hot')).toBeInTheDocument();
  });

  it('names a file over 20 MB and a file of the wrong type, and still uploads the others', async () => {
    mountLibrary();
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    drop([
      file('alpha.png'),
      file('huge.png', 'image/png', 21 * MB),
      file('anim.gif', 'image/gif'),
      file('beta.jpg', 'image/jpeg'),
    ]);

    await waitFor(() => expect(noticeText()).toContain('huge.png'));
    expect(noticeText()).toContain('anim.gif');

    fireEvent.click(uploadButton());
    await waitFor(() => expect(uploadAsset).toHaveBeenCalledTimes(2));
    expect(uploadedNames()).toEqual(['alpha.png', 'beta.jpg']);
    await waitFor(() => expect(tile('Beta')).toBeInTheDocument());
    expect(tile('Alpha')).toBeInTheDocument();
  });

  it('a file of exactly 20 MB is accepted', async () => {
    mountLibrary();
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    drop([file('edge.png', 'image/png', 20 * MB), file('alpha.png')]);
    fireEvent.click(uploadButton());
    await waitFor(() => expect(uploadAsset).toHaveBeenCalledTimes(2));
    expect(uploadedNames()).toEqual(['edge.png', 'alpha.png']);
  });
});

describe('AssetPickerDialog: onPickMany (AC-6.2)', () => {
  it('tiles toggle, the footer counts, and Done returns the sources in pick order', async () => {
    const { onPickMany, onPick, onCancel } = mountMany();
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());

    fireEvent.click(tile('Mixer'));
    expect(tile('Mixer')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/^1 selected$/)).toBeInTheDocument();

    fireEvent.click(tile('Hot'));
    fireEvent.click(tile('Cold'));
    fireEvent.click(tile('Cold'));
    expect(tile('Cold')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText(/^2 selected$/)).toBeInTheDocument();

    expect(onPick).not.toHaveBeenCalled();
    expect(onPickMany).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onPickMany).toHaveBeenCalledTimes(1);
    expect(onPickMany).toHaveBeenCalledWith([
      { type: 'asset', assetId: 'mixer' },
      { type: 'asset', assetId: 'hot' },
    ]);
    expect(onPick).not.toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('a product photo and library artwork are picked together, in pick order', async () => {
    const { onPickMany } = mountMany([
      { attachment_id: 'p1', url: 'https://cdn.test/p1.jpg', is_primary: true },
      { attachment_id: 'p2', url: 'https://cdn.test/p2.jpg', is_primary: false },
    ]);
    const photo = (url: string) => document.querySelector(`img[src="${url}"]`)!.closest('button')!;
    await waitFor(() => expect(photo('https://cdn.test/p2.jpg')).toBeTruthy());

    fireEvent.click(photo('https://cdn.test/p2.jpg'));
    expect(photo('https://cdn.test/p2.jpg')).toHaveAttribute('aria-pressed', 'true');

    const libraryTab = screen.getByRole('tab', { name: 'Asset library' });
    fireEvent.mouseDown(libraryTab, { button: 0 });
    fireEvent.click(libraryTab);
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    fireEvent.click(tile('Hot'));
    expect(screen.getByText(/^2 selected$/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onPickMany).toHaveBeenCalledWith([
      { type: 'product_attachment', attachmentId: 'p2' },
      { type: 'asset', assetId: 'hot' },
    ]);
  });

  it('files uploaded in this mode join the selection, after the earlier picks', async () => {
    const { onPickMany, onPick } = mountMany();
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    fireEvent.click(tile('Hot'));

    drop([file('alpha.png'), file('beta.png')]);
    fireEvent.click(uploadButton());
    await waitFor(() => expect(tile('Beta')).toBeInTheDocument());
    expect(uploadedNames()).toEqual(['alpha.png', 'beta.png']);
    expect(tile('Alpha')).toHaveAttribute('aria-pressed', 'true');
    expect(tile('Beta')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/^3 selected$/)).toBeInTheDocument();
    expect(onPick).not.toHaveBeenCalled();
    expect(onPickMany).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onPickMany).toHaveBeenCalledWith([
      { type: 'asset', assetId: 'hot' },
      { type: 'asset', assetId: 'alpha' },
      { type: 'asset', assetId: 'beta' },
    ]);
  });
});

describe('AssetPickerDialog: pick mode without onPickMany is unchanged (AC-6.2)', () => {
  it('one click picks and nothing toggles', async () => {
    const onPick = vi.fn();
    render(<AssetPickerDialog open productImages={[]} allowProductPhotos={false} onCancel={vi.fn()} onPick={onPick} />);
    await waitFor(() => expect(tile('Hot')).toBeInTheDocument());
    expect(tile('Hot')).not.toHaveAttribute('aria-pressed');
    fireEvent.click(tile('Hot'));
    expect(onPick).toHaveBeenCalledWith({ type: 'asset', assetId: 'hot' });
    expect(screen.queryByText(/selected$/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Done' })).toBeNull();
  });
});
