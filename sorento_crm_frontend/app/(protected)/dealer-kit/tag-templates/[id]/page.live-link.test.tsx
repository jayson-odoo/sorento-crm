/**
 * PRICETAG-ACCESSORY-DESIGNER fix round 2: the live link. A linked box with NO baseline follows the
 * server and is never pushed; a box edited against its baseline is pushed; corrections reach the live
 * canvas as patches (no remount).
 */
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('../components/TemplateRecordPager', () => ({ TemplateRecordPager: () => null }));
vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'tmpl-1' }),
  usePathname: () => '/dealer-kit/tag-templates/tmpl-1',
  useSearchParams: () => new URLSearchParams(),
}));
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
  listPublishedTemplates: vi.fn(async () => []),
  updateTemplateSettings: vi.fn(),
}));
vi.mock('../../tag-sizes/hooks/useTagSizes', () => ({
  useTagSizesQuery: () => ({ data: [] }),
  useDeleteTagSizePreset: () => ({ run: vi.fn(), targetId: null, isPending: false }),
  useCreateTagSize: () => ({ mutateAsync: vi.fn(async () => ({})), isPending: false }),
}));
vi.mock('../components/TagVersionViewer', () => ({ TagVersionViewer: () => null }));
vi.mock('../components/TemplateVersionsSheet', () => ({ TemplateVersionsSheet: () => null }));

const link = vi.hoisted(() => ({
  push: vi.fn(async () => ({})),
  fetch: vi.fn(),
  patches: vi.fn(),
}));
vi.mock('../../accessory-templates/hooks/useAccessoryTemplates', () => ({
  useUpdateAccessoryTemplate: () => ({ mutateAsync: link.push }),
  useFetchAccessoryTemplate: () => link.fetch,
  useRefreshAccessoryTemplates: () => vi.fn(),
}));

type Layer = { id: string; type: string; props: Record<string, unknown> };
vi.mock('../components/TagCanvasEditor', () => ({
  TagCanvasEditor: ({
    doc,
    onLayersChange,
    layerPatchesRef,
  }: {
    doc: { layers: Layer[] };
    onLayersChange?: (layers: Layer[]) => void;
    layerPatchesRef?: { current: unknown };
  }) => {
    if (layerPatchesRef) layerPatchesRef.current = link.patches;
    return (
      <div data-testid="canvas-editor">
        <button
          onClick={() =>
            onLayersChange?.(
              doc.layers.map((l) => ({ ...l, props: { ...l.props, headerText: 'EDITED' } })),
            )
          }
        >
          Edit the box
        </button>
        <button
          onClick={() =>
            onLayersChange?.([
              ...doc.layers,
              { id: 'box1', type: 'accessories', props: { kind: 'accessories', direction: 'vertical', headerText: 'STALE', presetId: 'p1' } },
            ])
          }
        >
          Paste a linked box
        </button>
      </div>
    );
  },
}));

import { getTemplate, updateTemplate } from '../../services/tagTemplateService';
import TagTemplateEditorPage from './page';

const box = (headerText: string): Layer => ({
  id: 'box1',
  type: 'accessories',
  props: { kind: 'accessories', direction: 'vertical', headerText, presetId: 'p1' },
});
const serverRecord = (headerText: string, updated_at = 'U1') =>
  ({ id: 'p1', name: 'FREE', used_in: 1, updated_at, design: { direction: 'vertical', headerText } }) as never;

function fixture(layers: Layer[]) {
  return {
    id: 'tmpl-1', name: 'T', family: 'toilet',
    doc: { layers, width_mm: 85, height_mm: 58 },
    print_size: { width_mm: 85, height_mm: 58 },
    created_at: '', updated_at: '', published_version_id: null, published_version_no: null,
  } as never;
}

async function editThenAutosave(label: string) {
  vi.useFakeTimers();
  try {
    fireEvent.click(screen.getByText(label));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
  } finally {
    vi.useRealTimers();
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe('live link on autosave', () => {
  it('does nothing until the baselines exist, then pushes the edit', async () => {
    vi.mocked(getTemplate).mockResolvedValue(fixture([box('OLD')]));
    vi.mocked(updateTemplate).mockResolvedValue(fixture([box('EDITED')]));
    let release: (value: unknown) => void = () => {};
    link.fetch
      .mockReturnValueOnce(new Promise((resolve) => (release = resolve)))
      .mockResolvedValue(serverRecord('OLD', 'U1'));
    render(<TagTemplateEditorPage />);
    await screen.findByTestId('canvas-editor');
    await editThenAutosave('Edit the box');
    expect(link.push).not.toHaveBeenCalled();
    await act(async () => {
      release(serverRecord('OLD', 'U1'));
    });
    await waitFor(() =>
      expect(link.push).toHaveBeenCalledWith({
        id: 'p1',
        input: { design: expect.objectContaining({ headerText: 'EDITED' }), base_updated_at: 'U1' },
      }),
    );
  });

  it('when the template was saved elsewhere since this tag loaded, nothing is pushed and the server design wins', async () => {
    vi.mocked(getTemplate).mockResolvedValue(fixture([box('OLD')]));
    vi.mocked(updateTemplate).mockResolvedValue(fixture([box('EDITED')]));
    // Loaded at U1; by the first save the template is at U2 with a newer design.
    link.fetch.mockResolvedValueOnce(serverRecord('OLD', 'U1')).mockResolvedValue(serverRecord('NEWER', 'U2'));
    render(<TagTemplateEditorPage />);
    await screen.findByTestId('canvas-editor');
    await editThenAutosave('Edit the box');
    expect(link.push).not.toHaveBeenCalled();
    const [patches] = link.patches.mock.calls[0] as unknown as [{ props: { headerText: string } }[]];
    expect(patches[0].props.headerText).toBe('NEWER');
  });

  it('a box that was already linked and is edited is pushed to its template', async () => {
    vi.mocked(getTemplate).mockResolvedValue(fixture([box('OLD')]));
    vi.mocked(updateTemplate).mockResolvedValue(fixture([box('EDITED')]));
    link.fetch.mockResolvedValue(serverRecord('OLD'));
    render(<TagTemplateEditorPage />);
    await screen.findByTestId('canvas-editor');
    await editThenAutosave('Edit the box');
    expect(link.push).toHaveBeenCalledWith({
      id: 'p1',
      input: { design: expect.objectContaining({ headerText: 'EDITED' }), base_updated_at: 'U1' },
    });
  });

  it('a box with no baseline follows the server and is never pushed', async () => {
    // Loaded with no linked box; one then appears (inserted from a stale menu, pasted from another tab).
    vi.mocked(getTemplate).mockResolvedValue(fixture([]));
    vi.mocked(updateTemplate).mockResolvedValue(fixture([]));
    link.fetch.mockResolvedValue(serverRecord('SERVER'));
    render(<TagTemplateEditorPage />);
    await screen.findByTestId('canvas-editor');
    await editThenAutosave('Paste a linked box');
    expect(link.push).not.toHaveBeenCalled();
    expect(link.patches).toHaveBeenCalledTimes(1);
    const [patches] = link.patches.mock.calls[0] as unknown as [{ layerId: string; props: { headerText: string } }[]];
    expect(patches[0].layerId).toBe('box1');
    expect(patches[0].props.headerText).toBe('SERVER');
  });

  it('a deleted template detaches the box on the live canvas, keeping its design', async () => {
    vi.mocked(getTemplate).mockResolvedValue(fixture([box('OLD')]));
    vi.mocked(updateTemplate).mockResolvedValue(fixture([box('OLD')]));
    link.fetch.mockResolvedValue(null);
    render(<TagTemplateEditorPage />);
    await screen.findByTestId('canvas-editor');
    await editThenAutosave('Edit the box');
    expect(link.push).not.toHaveBeenCalled();
    const [patches] = link.patches.mock.calls[0] as unknown as [{ props: { presetId: unknown; headerText: string } }[]];
    expect(patches[0].props.presetId).toBeNull();
    expect(patches[0].props.headerText).toBe('EDITED');
  });
});
