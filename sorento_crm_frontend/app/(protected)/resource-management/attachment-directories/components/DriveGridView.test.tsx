/**
 * DriveGridView — unified folders+files cards (UAC A4, A6/A7, F1, G2).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DndContext } from '@dnd-kit/core';

import DriveGridView from './DriveGridView';
import type { DriveItem } from '../../attachments/services/driveService';

// The image card lazily resolves a serve URL; stub it so a thumbnail never fetches.
vi.mock('./DriveImageThumbnail', () => ({
  default: () => <div data-testid="lazy-thumb" />,
}));

const items: DriveItem[] = [
  { kind: 'folder', id: 'fold-1', name: 'Campaigns', parent_id: null, sort_order: 0 },
  {
    kind: 'file',
    id: 'file-1',
    original_filename: 'brief.pdf',
    stored_filename: 'brief.pdf',
    file_path: 'p',
    mime_type: 'application/pdf',
    uploaded_at: '2026-01-01',
    is_deleted: false,
  } as DriveItem,
  {
    kind: 'file',
    id: 'file-2',
    original_filename: 'banner.png',
    stored_filename: 'banner.png',
    file_path: 'p',
    mime_type: 'image/png',
    uploaded_at: '2026-01-01',
    is_deleted: false,
  } as DriveItem,
];

beforeEach(() => {
  // dnd-kit reads matchMedia.
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((q: string) => ({
      matches: false,
      media: q,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderGrid(props?: Partial<React.ComponentProps<typeof DriveGridView>>) {
  const onOpen = vi.fn();
  const onToggleSelect = vi.fn();
  render(
    <DndContext>
      <DriveGridView
        items={items}
        selectedIds={[]}
        draggable={false}
        currentDirectoryId={null}
        onOpen={onOpen}
        onToggleSelect={onToggleSelect}
        {...props}
      />
    </DndContext>
  );
  return { onOpen, onToggleSelect };
}

describe('DriveGridView', () => {
  it('A4: renders folders AND files as cards in the same collection', () => {
    renderGrid();
    expect(screen.getByText('Campaigns')).toBeInTheDocument();
    expect(screen.getByText('brief.pdf')).toBeInTheDocument();
    expect(screen.getByText('banner.png')).toBeInTheDocument();
    expect(screen.getAllByTestId('drive-card-folder')).toHaveLength(1);
    expect(screen.getAllByTestId('drive-card-file')).toHaveLength(2);
  });

  it('G2: an image file renders the lazy thumbnail; non-image files do not', () => {
    renderGrid();
    // Only banner.png (image/png) gets the lazy thumbnail.
    expect(screen.getAllByTestId('lazy-thumb')).toHaveLength(1);
  });

  it('A6/A7: clicking a card body opens the item', () => {
    const { onOpen } = renderGrid();
    fireEvent.click(screen.getByText('Campaigns'));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 'fold-1', kind: 'folder' }));
  });

  it('F1: toggling a card checkbox selects without opening', () => {
    const { onToggleSelect, onOpen } = renderGrid();
    const checkbox = screen.getByLabelText('Select brief.pdf');
    fireEvent.click(checkbox);
    expect(onToggleSelect).toHaveBeenCalledWith('file-1', true);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('shows an empty state when there are no items', () => {
    renderGrid({ items: [] });
    expect(screen.getByText(/this folder is empty/i)).toBeInTheDocument();
  });

  it('right-click opens the per-card context menu (parity with list view)', () => {
    const renderRowContextMenu = vi.fn((item: DriveItem) => (
      <div role="menuitem">Menu for {item.id}</div>
    ));
    renderGrid({ renderRowContextMenu });
    const card = screen.getAllByTestId('drive-card-file')[0];
    fireEvent.contextMenu(card);
    expect(renderRowContextMenu).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'file-1', kind: 'file' })
    );
    expect(screen.getByText('Menu for file-1')).toBeInTheDocument();
  });
});
