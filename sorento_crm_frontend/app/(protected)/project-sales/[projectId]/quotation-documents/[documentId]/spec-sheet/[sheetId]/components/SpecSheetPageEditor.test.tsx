/**
 * The spec sheet page editor feeds the designer the design call's MEDIUM urls (owner rule: screens
 * never load full-size originals). A pasted library asset in the page must reach `TagCanvasEditor`
 * as its medium url, so the editor never resolves it to the library's original.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
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

const getSpecSheet = vi.fn();
const getSpecSheetPageDesign = vi.fn();
vi.mock('@/app/(protected)/project-sales/_shared/services/specSheetService', () => ({
  getSpecSheet: (...a: unknown[]) => getSpecSheet(...a),
  getSpecSheetPageDesign: (...a: unknown[]) => getSpecSheetPageDesign(...a),
  saveSpecSheetPageEdit: vi.fn(),
  updateSpecSheet: vi.fn(),
  listSpecSheets: vi.fn(),
  createSpecSheet: vi.fn(),
  getSpecSheetPreview: vi.fn(),
  getSpecSheetPageImages: vi.fn(),
  queueSpecSheetPdf: vi.fn(),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(async () => ({ pending: null, last_outcome: null })),
}));
vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => undefined),
  ensureSeedFontsLoaded: vi.fn(async () => undefined),
}));

// The library-original fetcher: the editor's own hook. It must never be what draws a supplied asset.
const libraryOriginalFor = vi.fn();
let editorProps: Record<string, unknown> = {};
vi.mock('@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor', () => ({
  TagCanvasEditor: (props: Record<string, unknown>) => {
    editorProps = props;
    const urls = (props.assetUrls ?? {}) as Record<string, string>;
    // What the real editor does per asset layer: the host url wins, else the library original.
    const layers = (props.doc as { layers: { props: { source?: { assetId?: string } } }[] }).layers;
    const drawn = layers.map((layer) => {
      const id = layer.props.source?.assetId as string;
      return urls[id] ?? libraryOriginalFor(id);
    });
    return <div data-testid="editor" data-drawn={drawn.join(',')} />;
  },
}));

import { SpecSheetPageEditor } from './SpecSheetPageEditor';

const MEDIUM = 'https://cdn.test/logo.medium.jpg';

beforeEach(() => {
  editorProps = {};
  libraryOriginalFor.mockReset().mockReturnValue('https://cdn.test/logo-original-7mb.png');
  getSpecSheet.mockReset().mockResolvedValue({ id: 's1', label: 'SS1', source_label: 'R1', pages: [] });
  getSpecSheetPageDesign.mockReset().mockResolvedValue({
    layers: [{ id: 'l1', type: 'image', props: { kind: 'image', source: { type: 'asset', assetId: 'a1' } } }],
    bound: { code: 'X', images: [], parts: [] },
    images: {},
    assets: { a1: MEDIUM },
    fonts: [],
    width_mm: 338.7,
    height_mm: 190.5,
    template_name: 'Page',
    template_id: 't1',
    edited: true,
  });
});

describe('SpecSheetPageEditor', () => {
  it('hands the designer the medium asset urls, so the library original is never used', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <SpecSheetPageEditor projectId="p1" documentId="d1" sheetId="s1" pageKey="k1" />
      </QueryClientProvider>,
    );

    const editor = await screen.findByTestId('editor');
    await waitFor(() => expect(editor).toHaveAttribute('data-drawn', MEDIUM));
    expect(editorProps.assetUrls).toEqual({ a1: MEDIUM });
    expect(libraryOriginalFor).not.toHaveBeenCalled();
  });
});
