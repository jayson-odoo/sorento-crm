/**
 * AC-C10: the block palette must not offer Artboard.
 *
 * The `artboard` BlockType, its factory case in `newBlock`, and BlockPreview's
 * placeholder rendering are all kept - a document seeded or saved before this
 * change may already carry an artboard block and must keep rendering, not
 * crash. Only the palette ENTRY that lets a designer place a NEW one is gone,
 * because the block is a stub: it renders a placeholder and never gets a real
 * sub-canvas or an inspector case. This test pins the palette contents so the
 * stub cannot quietly come back.
 */
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../services/catalogueService', () => ({
  createCollection: vi.fn(),
  listBundles: vi.fn().mockResolvedValue([]),
  listCollections: vi.fn().mockResolvedValue([]),
  listTileTemplates: vi.fn().mockResolvedValue([]),
  resolveBundle: vi.fn(),
  resolveCollection: vi.fn(),
  saveCollectionAsLibrary: vi.fn(),
  updateCollection: vi.fn(),
}));

import { PageEditor } from './PageEditor';
import type { PageDoc } from '@/lib/dealer-kit/types';

const EMPTY_DOC: PageDoc = {
  sections: [
    {
      id: 'sec-1',
      name: 'Section 1',
      style: { background: 'transparent', paddingY: 'lg' },
      blocks: [],
      layouts: {
        desktop: { blocks: {}, isDerived: false },
        tablet: { blocks: {}, isDerived: true },
        mobile: { blocks: {}, isDerived: true },
      },
      printMode: 'include',
    },
  ],
  printProfile: {
    pageSize: 'A4',
    orientation: 'portrait',
    margins: { top: 0, right: 0, bottom: 0, left: 0 },
    cover: false,
    headerFooter: { left: '', right: '', pageNumbers: false },
  },
};

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PageEditor pageId="pg-1" doc={EMPTY_DOC} onDocChange={() => {}} />
    </QueryClientProvider>,
  );
}

describe('PageEditor block palette', () => {
  it('offers the real block types', () => {
    renderEditor();

    expect(screen.getByRole('button', { name: /heading/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^text$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^image$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /products/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /bundle/i })).toBeInTheDocument();
  });

  it('does not offer Artboard', () => {
    renderEditor();

    expect(screen.queryByRole('button', { name: /artboard/i })).toBeNull();
  });
});
