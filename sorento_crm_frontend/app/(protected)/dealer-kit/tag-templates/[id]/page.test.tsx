/**
 * Template editor page chrome (S5, AC-S5-5/S5-8): the header states (Draft /
 * Live vN), Save writes the draft, Publish moves the pointer, and View swaps
 * to a read-only render of a past version WITHOUT losing the in-memory
 * draft - closing it (Back to draft) shows the editor again with the same
 * doc it had before View was opened.
 *
 * `TagCanvasEditor` and `TagVersionViewer` are Konva-backed and jsdom has no
 * canvas, so both are replaced with tiny stand-ins that expose just enough
 * to assert the host's wiring (same idiom as other dealer-kit page tests
 * stubbing heavy children).
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { toast } from 'sonner';
const mockToastSuccess = vi.mocked(toast.success);

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'tmpl-1' }),
  usePathname: () => '/dealer-kit/tag-templates/tmpl-1',
  useSearchParams: () => new URLSearchParams(),
}));

// Container pulls SettingsProvider context this unit test does not need.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../../services/tagTemplateService', () => ({
  getTemplate: vi.fn(),
  updateTemplate: vi.fn(),
  publishTemplate: vi.fn(),
  restoreTemplateVersion: vi.fn(),
  getTemplateVersion: vi.fn(),
  listTemplateVersions: vi.fn(),
}));

vi.mock('../components/TagCanvasEditor', () => ({
  TagCanvasEditor: ({
    doc,
    onLayersChange,
  }: {
    doc: { layers: { id: string }[] };
    onLayersChange?: (layers: { id: string }[]) => void;
  }) => (
    <div data-testid="canvas-editor">
      editor: {doc.layers.length} layers
      {/* Simulates an in-canvas edit that has NOT been Saved yet - the same
          stream the real canvas sends on every layer change (B1, S1). */}
      <button
        onClick={() =>
          onLayersChange?.([...doc.layers, { id: `new-${doc.layers.length}` }])
        }
      >
        Add a layer
      </button>
    </div>
  ),
}));

vi.mock('../components/TagVersionViewer', () => ({
  TagVersionViewer: ({
    doc,
    versionNo,
    onBackToDraft,
    onRestore,
    restoring,
  }: {
    doc: { layers: unknown[] };
    versionNo: number;
    onBackToDraft: () => void;
    onRestore: () => void;
    restoring?: boolean;
  }) => (
    <div data-testid="version-viewer">
      Viewing v{versionNo} - read-only ({doc.layers.length} layers)
      <button onClick={onBackToDraft}>Back to draft</button>
      <button onClick={onRestore} disabled={restoring}>
        {restoring ? 'Restoring...' : 'Restore this version'}
      </button>
    </div>
  ),
}));

vi.mock('../components/TemplateVersionsSheet', () => ({
  TemplateVersionsSheet: ({
    open,
    onView,
  }: {
    open: boolean;
    onView: (id: string, versionNo: number) => void;
  }) =>
    open ? (
      <div data-testid="versions-sheet">
        <button onClick={() => onView('v1', 1)}>View v1</button>
      </div>
    ) : null,
}));

import {
  getTemplate,
  getTemplateVersion,
  publishTemplate,
  restoreTemplateVersion,
  updateTemplate,
} from '../../services/tagTemplateService';
import TagTemplateEditorPage from './page';

const mockGet = vi.mocked(getTemplate);
const mockUpdate = vi.mocked(updateTemplate);
const mockPublish = vi.mocked(publishTemplate);
const mockGetVersion = vi.mocked(getTemplateVersion);
const mockRestore = vi.mocked(restoreTemplateVersion);

function templateFixture(overrides: Partial<Awaited<ReturnType<typeof getTemplate>>> = {}) {
  return {
    id: 'tmpl-1',
    name: 'Toilet family tag',
    family: 'toilet',
    doc: { layers: [{ id: 'l1' }], width_mm: 85, height_mm: 58 },
    print_size: { width_mm: 85, height_mm: 58 },
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    published_version_id: null,
    published_version_no: null,
    ...overrides,
  } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Header states (AC-S5-5)
// ---------------------------------------------------------------------------

describe('header badge', () => {
  it('reads Draft when never published', async () => {
    mockGet.mockResolvedValue(templateFixture());
    render(<TagTemplateEditorPage />);

    expect(await screen.findByText('Draft')).toBeInTheDocument();
  });

  it('reads Live vN once published', async () => {
    mockGet.mockResolvedValue(
      templateFixture({ published_version_id: 'v3', published_version_no: 3 }),
    );
    render(<TagTemplateEditorPage />);

    expect(await screen.findByText('Live v3')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Full screen (S7, AC-S6-1): the shared FocusShell, same as the room designer.
// ---------------------------------------------------------------------------

it('Full screen wraps the canvas in the shared FocusShell, and Escape exits', async () => {
  mockGet.mockResolvedValue(templateFixture());
  render(<TagTemplateEditorPage />);

  await screen.findByTestId('canvas-editor');
  expect(document.querySelector('[data-dk-focus-mode]')).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: /Full screen/ }));
  expect(document.querySelector('[data-dk-focus-mode]')).not.toBeNull();
  // The canvas is still the same content, now inside the overlay.
  expect(screen.getByTestId('canvas-editor')).toBeInTheDocument();

  fireEvent.keyDown(document, { key: 'Escape' });
  expect(document.querySelector('[data-dk-focus-mode]')).toBeNull();
});

// ---------------------------------------------------------------------------
// Save (header, not the canvas's own bar - AC-S5-5)
// ---------------------------------------------------------------------------

it('Save writes the draft through updateTemplate', async () => {
  mockGet.mockResolvedValue(templateFixture());
  mockUpdate.mockResolvedValue(templateFixture());
  render(<TagTemplateEditorPage />);

  await screen.findByTestId('canvas-editor');
  fireEvent.click(screen.getByRole('button', { name: /Save/ }));

  await waitFor(() =>
    expect(mockUpdate).toHaveBeenCalledWith(
      'tmpl-1',
      expect.objectContaining({ layers: [{ id: 'l1' }] }),
    ),
  );
});

// ---------------------------------------------------------------------------
// Publish (AC-S5-1)
// ---------------------------------------------------------------------------

it('Publish sends the note and updates the badge on success', async () => {
  mockGet.mockResolvedValue(templateFixture());
  mockUpdate.mockResolvedValue(templateFixture());
  mockPublish.mockResolvedValue(
    templateFixture({ published_version_id: 'v1', published_version_no: 1 }),
  );
  render(<TagTemplateEditorPage />);

  await screen.findByTestId('canvas-editor');
  fireEvent.click(screen.getByRole('button', { name: /Publish/ }));
  fireEvent.change(await screen.findByLabelText('Note (optional)'), {
    target: { value: 'first release' },
  });
  const dialog = within(screen.getByRole('dialog'));
  fireEvent.click(dialog.getByRole('button', { name: 'Publish' }));

  await waitFor(() => expect(mockPublish).toHaveBeenCalledWith('tmpl-1', 'first release'));
  expect(await screen.findByText('Live v1')).toBeInTheDocument();
});

it('Publish persists an unsaved draft edit BEFORE snapshotting it (S1)', async () => {
  // Publish used to snapshot whatever the backend last had saved, silently
  // dropping any edit made since the last manual Save. The fix: Publish
  // writes the current draft first, THEN publishes what it just wrote.
  mockGet.mockResolvedValue(templateFixture());
  mockUpdate.mockResolvedValue(
    templateFixture({ doc: { layers: [{ id: 'l1' }, { id: 'new-1' }], width_mm: 85, height_mm: 58 } as never }),
  );
  mockPublish.mockResolvedValue(
    templateFixture({ published_version_id: 'v1', published_version_no: 1 }),
  );
  render(<TagTemplateEditorPage />);

  await screen.findByTestId('canvas-editor');
  // An edit that has NOT been Saved.
  fireEvent.click(screen.getByText('Add a layer'));
  expect(screen.getByText('editor: 2 layers')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Publish/ }));
  const dialog = within(screen.getByRole('dialog'));
  fireEvent.click(dialog.getByRole('button', { name: 'Publish' }));

  await waitFor(() =>
    expect(mockUpdate).toHaveBeenCalledWith(
      'tmpl-1',
      expect.objectContaining({ layers: [{ id: 'l1' }, { id: 'new-1' }] }),
    ),
  );
  // Publish runs on what updateTemplate just persisted, not the stale id/doc.
  await waitFor(() => expect(mockPublish).toHaveBeenCalledWith('tmpl-1', undefined));
  // updateTemplate must resolve before publishTemplate is called - the whole
  // point of S1 is that Publish reads the SAVED draft, not the in-flight one.
  const updateOrder = mockUpdate.mock.invocationCallOrder[0];
  const publishOrder = mockPublish.mock.invocationCallOrder[0];
  expect(updateOrder).toBeLessThan(publishOrder);
});

// ---------------------------------------------------------------------------
// View read-only + draft intact after returning (D16, AC-S5-8)
// ---------------------------------------------------------------------------

it('View swaps to the read-only viewer and Back to draft restores the SAME draft', async () => {
  mockGet.mockResolvedValue(templateFixture());
  mockGetVersion.mockResolvedValue({
    id: 'v1',
    template_id: 'tmpl-1',
    version_no: 1,
    note: null,
    created_by: null,
    created_by_name: null,
    created_at: '2026-08-01T00:00:00Z',
    doc: { layers: [{ id: 'old-layer' }], width_mm: 85, height_mm: 58 },
    print_size: { width_mm: 85, height_mm: 58 },
  } as never);
  render(<TagTemplateEditorPage />);

  await screen.findByTestId('canvas-editor');
  expect(screen.getByText('editor: 1 layers')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Versions/ }));
  fireEvent.click(await screen.findByText('View v1'));

  const viewer = await screen.findByTestId('version-viewer');
  expect(viewer.textContent).toContain('Viewing v1 - read-only');
  expect(viewer.textContent).toContain('1 layers');
  // The editor stays MOUNTED underneath the viewer (B1 fix) - it is not in
  // the accessibility tree while hidden, but it never left the DOM, which is
  // exactly what stops the mount-reset bug below.
  expect(screen.getByTestId('canvas-editor')).toBeInTheDocument();

  fireEvent.click(screen.getByText('Back to draft'));

  // The draft the editor shows is exactly what it had before View - the
  // template's OWN doc (1 layer), not the version's (also 1, so the layer id
  // asserted below is what actually distinguishes them).
  await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
  expect(screen.getByText('editor: 1 layers')).toBeInTheDocument();
  expect(mockUpdate).not.toHaveBeenCalled();
});

it('an unsaved draft edit survives opening View and Back to draft (B1)', async () => {
  mockGet.mockResolvedValue(templateFixture());
  mockGetVersion.mockResolvedValue({
    id: 'v1',
    template_id: 'tmpl-1',
    version_no: 1,
    note: null,
    created_by: null,
    created_by_name: null,
    created_at: '2026-08-01T00:00:00Z',
    doc: { layers: [{ id: 'old-layer' }], width_mm: 85, height_mm: 58 },
    print_size: { width_mm: 85, height_mm: 58 },
  } as never);
  render(<TagTemplateEditorPage />);

  await screen.findByTestId('canvas-editor');
  expect(screen.getByText('editor: 1 layers')).toBeInTheDocument();

  // An in-canvas edit that has NOT been Saved - the mount-reset bug (B1)
  // used to wipe exactly this the moment View opened the read-only viewer.
  fireEvent.click(screen.getByText('Add a layer'));
  expect(screen.getByText('editor: 2 layers')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /Versions/ }));
  fireEvent.click(await screen.findByText('View v1'));
  await screen.findByTestId('version-viewer');

  fireEvent.click(screen.getByText('Back to draft'));

  await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
  expect(screen.getByText('editor: 2 layers')).toBeInTheDocument();
  expect(mockUpdate).not.toHaveBeenCalled();
});

it('Restore from the viewer copies the version into the draft and returns to the editor', async () => {
  mockGet.mockResolvedValue(templateFixture());
  mockGetVersion.mockResolvedValue({
    id: 'v1',
    template_id: 'tmpl-1',
    version_no: 1,
    note: null,
    created_by: null,
    created_by_name: null,
    created_at: '2026-08-01T00:00:00Z',
    doc: { layers: [{ id: 'a' }, { id: 'b' }], width_mm: 85, height_mm: 58 },
    print_size: { width_mm: 85, height_mm: 58 },
  } as never);
  mockRestore.mockResolvedValue(
    templateFixture({
      doc: { layers: [{ id: 'a' }, { id: 'b' }], width_mm: 85, height_mm: 58 } as never,
    }),
  );
  render(<TagTemplateEditorPage />);

  await screen.findByTestId('canvas-editor');
  fireEvent.click(screen.getByRole('button', { name: /Versions/ }));
  fireEvent.click(await screen.findByText('View v1'));
  await screen.findByTestId('version-viewer');

  fireEvent.click(screen.getByText('Restore this version'));

  await waitFor(() => expect(mockRestore).toHaveBeenCalledWith('tmpl-1', 'v1'));
  await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
  expect(screen.getByText('editor: 2 layers')).toBeInTheDocument();
});

// ---------------------------------------------------------------------------
// Restore: no confirm dialog, runs immediately, Undo toast (B2 captain
// ruling 2 Sep - AlertDialog confirm is retired)
// ---------------------------------------------------------------------------

it('Restore from the viewer shows the restoring state and offers Undo', async () => {
  mockGet.mockResolvedValue(templateFixture());
  mockGetVersion.mockResolvedValue({
    id: 'v1',
    template_id: 'tmpl-1',
    version_no: 1,
    note: null,
    created_by: null,
    created_by_name: null,
    created_at: '2026-08-01T00:00:00Z',
    doc: { layers: [{ id: 'a' }, { id: 'b' }], width_mm: 85, height_mm: 58 },
    print_size: { width_mm: 85, height_mm: 58 },
  } as never);
  let resolveRestore: (v: unknown) => void = () => {};
  mockRestore.mockReturnValue(
    new Promise((resolve) => {
      resolveRestore = resolve;
    }) as never,
  );
  render(<TagTemplateEditorPage />);

  await screen.findByTestId('canvas-editor');
  fireEvent.click(screen.getByRole('button', { name: /Versions/ }));
  fireEvent.click(await screen.findByText('View v1'));
  await screen.findByTestId('version-viewer');

  // No confirm dialog anywhere - the click goes straight to the service call.
  fireEvent.click(screen.getByText('Restore this version'));
  expect(mockRestore).toHaveBeenCalledWith('tmpl-1', 'v1');
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByText('Restoring...')).toBeInTheDocument());

  resolveRestore(
    templateFixture({
      doc: { layers: [{ id: 'a' }, { id: 'b' }], width_mm: 85, height_mm: 58 } as never,
    }),
  );

  await waitFor(() => expect(mockToastSuccess).toHaveBeenCalledWith(
    'Draft restored',
    expect.objectContaining({ action: expect.objectContaining({ label: 'Undo' }) }),
  ));

  // Undo PUTs the pre-restore draft straight back.
  mockUpdate.mockResolvedValue(templateFixture());
  const [, options] = mockToastSuccess.mock.calls[0];
  await (options as unknown as { action: { onClick: () => Promise<void> } }).action.onClick();

  expect(mockUpdate).toHaveBeenCalledWith(
    'tmpl-1',
    expect.objectContaining({ layers: [{ id: 'l1' }] }),
  );
});
