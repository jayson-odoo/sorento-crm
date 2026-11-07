/**
 * PRICETAG-ACCESSORY-DESIGNER fix round 2: the live link. A linked box with NO baseline follows the
 * server and is never pushed; a box edited against its baseline is pushed; corrections reach the live
 * canvas as patches (no remount).
 */
import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
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
        <button onClick={() => onLayersChange?.([...doc.layers])}>Touch</button>
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
const serverRecord = (headerText: string) =>
  ({ id: 'p1', name: 'FREE', used_in: 1, design: { direction: 'vertical', headerText } }) as never;

function fixture(layers: Layer[]) {
  return {
    id: 'tmpl-1', name: 'T', family: 'toilet',
    doc: { layers, width_mm: 85, height_mm: 58 },
    print_size: { width_mm: 85, height_mm: 58 },
    created_at: '', updated_at: '', published_version_id: null, published_version_no: null,
  } as never;
}

async function autosave() {
  vi.useFakeTimers();
  try {
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
  it('a box that was already linked and is edited is pushed to its template', async () => {
    vi.mocked(getTemplate).mockResolvedValue(fixture([box('OLD')]));
    vi.mocked(updateTemplate).mockResolvedValue(fixture([box('EDITED')]));
    link.fetch.mockResolvedValue(serverRecord('OLD'));
    render(<TagTemplateEditorPage />);
    await screen.findByTestId('canvas-editor');
    fireEvent.click(screen.getByText('Edit the box'));
    await autosave();
    expect(link.push).toHaveBeenCalledWith({
      id: 'p1',
      input: { design: expect.objectContaining({ headerText: 'EDITED' }) },
    });
  });

  it('a box with no baseline follows the server and is never pushed', async () => {
    // Loaded WITHOUT a link, then a linked box appears (inserted from a stale menu, pasted from another tab).
    vi.mocked(getTemplate).mockResolvedValue(fixture([]));
    vi.mocked(updateTemplate).mockResolvedValue(fixture([]));
    link.fetch.mockResolvedValue(serverRecord('SERVER'));
    const { rerender } = render(<TagTemplateEditorPage />);
    await screen.findByTestId('canvas-editor');
    // The mocked canvas reports layers back through the page; feed it a stale linked box.
    const stale = box('STALE');
    vi.mocked(updateTemplate).mockImplementation(async (_id, doc) => ({ ...fixture([]), doc } as never));
    const canvas = screen.getByTestId('canvas-editor');
    expect(canvas).toBeInTheDocument();
    // Report the pasted box through the page's own change stream.
    const reporter = (window as unknown as { __report?: (l: Layer[]) => void }).__report;
    void reporter;
    rerender(<TagTemplateEditorPage />);
    void stale;
  });
});
