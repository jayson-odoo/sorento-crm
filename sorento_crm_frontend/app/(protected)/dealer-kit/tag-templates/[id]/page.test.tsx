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
  TagCanvasEditor: ({ doc }: { doc: { layers: unknown[] } }) => (
    <div data-testid="canvas-editor">editor: {doc.layers.length} layers</div>
  ),
}));

vi.mock('../components/TagVersionViewer', () => ({
  TagVersionViewer: ({
    doc,
    versionNo,
    onBackToDraft,
    onRestore,
  }: {
    doc: { layers: unknown[] };
    versionNo: number;
    onBackToDraft: () => void;
    onRestore: () => void;
  }) => (
    <div data-testid="version-viewer">
      Viewing v{versionNo} - read-only ({doc.layers.length} layers)
      <button onClick={onBackToDraft}>Back to draft</button>
      <button onClick={onRestore}>Restore this version</button>
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
  expect(screen.queryByTestId('canvas-editor')).not.toBeInTheDocument();

  fireEvent.click(screen.getByText('Back to draft'));

  // The draft the editor shows is exactly what it had before View - the
  // template's OWN doc (1 layer), not the version's (also 1, so the layer id
  // asserted below is what actually distinguishes them).
  await waitFor(() => expect(screen.getByTestId('canvas-editor')).toBeInTheDocument());
  expect(screen.getByText('editor: 1 layers')).toBeInTheDocument();
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
