/**
 * DriveGridView drop-target highlight (review E). dnd-kit pointer drags can't run
 * in jsdom, so we mock @dnd-kit/core's useDroppable to assert the over-state
 * styling logic: a folder card hovered by a drag gets a strong ring + bg tint.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import type { DriveItem } from '../../attachments/services/driveService';

vi.mock('./DriveImageThumbnail', () => ({
  default: () => <div data-testid="lazy-thumb" />,
}));

// Force every droppable to report isOver -> exercises the highlight branch.
vi.mock('@dnd-kit/core', async () => {
  const actual = await vi.importActual<typeof import('@dnd-kit/core')>('@dnd-kit/core');
  return {
    ...actual,
    useDroppable: () => ({ setNodeRef: vi.fn(), isOver: true }),
    useDraggable: () => ({
      attributes: {},
      listeners: {},
      setNodeRef: vi.fn(),
      isDragging: false,
    }),
  };
});

import DriveGridView from './DriveGridView';
import { DndContext } from '@dnd-kit/core';

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
];

beforeEach(() => {
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

describe('DriveGridView drop highlight', () => {
  it('a folder card hovered by a drag gets a strong ring + bg highlight', () => {
    render(
      <DndContext>
        <DriveGridView
          items={items}
          selectedIds={[]}
          draggable
          currentDirectoryId={null}
          onOpen={vi.fn()}
          onToggleSelect={vi.fn()}
        />
      </DndContext>
    );
    const folderCard = screen.getByTestId('drive-card-folder');
    // The over-state branch applies a ring AND a tinted background.
    expect(folderCard.className).toContain('ring-primary');
    expect(folderCard.className).toContain('bg-primary/10');
  });
});
