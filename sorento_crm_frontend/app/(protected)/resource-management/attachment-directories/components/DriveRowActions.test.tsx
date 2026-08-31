/**
 * DriveRowActions - per-row right-click / long-press context-menu items that
 * replaced the actions column (review C). Verifies item presence + folder/file
 * and trash gating.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import DriveRowActions, { type DriveRowActionHandlers } from './DriveRowActions';
import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from '@/components/ui/context-menu';
import type { DriveItem } from '../../attachments/services/driveService';

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

const noopHandlers: DriveRowActionHandlers = {
  onOpen: vi.fn(),
  onPreview: vi.fn(),
  onDownload: vi.fn(),
  onRevealInFolder: vi.fn(),
  onRename: vi.fn(),
  onMove: vi.fn(),
  onSetCompany: vi.fn(),
  onResubmit: vi.fn(),
  onRestore: vi.fn(),
  onDelete: vi.fn(),
  onRenameFolder: vi.fn(),
  onNewSubfolder: vi.fn(),
  onDeleteFolder: vi.fn(),
};

const fileItem: DriveItem = {
  kind: 'file',
  id: 'file-1',
  original_filename: 'brief.pdf',
  stored_filename: 'brief.pdf',
  file_path: 'p',
  mime_type: 'application/pdf',
  uploaded_at: '2026-01-01',
  is_deleted: false,
} as DriveItem;

const folderItem: DriveItem = {
  kind: 'folder',
  id: 'fold-1',
  name: 'Campaigns',
  parent_id: null,
  sort_order: 0,
};

function renderActions(props: Partial<React.ComponentProps<typeof DriveRowActions>>) {
  render(
    <ContextMenu>
      <ContextMenuTrigger data-testid="row">Row</ContextMenuTrigger>
      <ContextMenuContent>
        <DriveRowActions
          item={fileItem}
          isTrashView={false}
          recursive={false}
          resubmitting={false}
          handlers={noopHandlers}
          {...props}
        />
      </ContextMenuContent>
    </ContextMenu>
  );
  // Right-click opens the Radix context menu (same path as long-press on touch).
  fireEvent.contextMenu(screen.getByTestId('row'));
}

describe('DriveRowActions', () => {
  it('file row (default): open/preview/download/rename/move/resubmit/move-to-trash', () => {
    renderActions({ item: fileItem });
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByText('Preview')).toBeInTheDocument();
    expect(screen.getByText('Download')).toBeInTheDocument();
    expect(screen.getByText('Rename')).toBeInTheDocument();
    expect(screen.getByText('Move to…')).toBeInTheDocument();
    expect(screen.getByText('Resubmit to n8n')).toBeInTheDocument();
    expect(screen.getByText('Move to trash')).toBeInTheDocument();
    // Folder-only actions never appear on a file row.
    expect(screen.queryByText('New subfolder')).not.toBeInTheDocument();
    // Reveal-in-folder only in recursive scope.
    expect(screen.queryByText('Reveal in folder')).not.toBeInTheDocument();
  });

  it('file row in recursive scope adds "Reveal in folder"', () => {
    renderActions({ item: fileItem, recursive: true });
    expect(screen.getByText('Reveal in folder')).toBeInTheDocument();
  });

  it('file row in trash: Restore + Permanently delete, no rename/resubmit', () => {
    renderActions({ item: fileItem, isTrashView: true });
    expect(screen.getByText('Restore')).toBeInTheDocument();
    expect(screen.getByText('Permanently delete')).toBeInTheDocument();
    expect(screen.queryByText('Rename')).not.toBeInTheDocument();
    expect(screen.queryByText('Resubmit to n8n')).not.toBeInTheDocument();
    expect(screen.queryByText('Move to trash')).not.toBeInTheDocument();
  });

  it('folder row: open/new subfolder/rename/move/delete, no file actions', () => {
    renderActions({ item: folderItem });
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByText('New subfolder')).toBeInTheDocument();
    expect(screen.getByText('Rename')).toBeInTheDocument();
    expect(screen.getByText('Move to…')).toBeInTheDocument();
    expect(screen.getByText('Delete')).toBeInTheDocument();
    // File-only actions are absent on a folder row.
    expect(screen.queryByText('Preview')).not.toBeInTheDocument();
    expect(screen.queryByText('Download')).not.toBeInTheDocument();
    expect(screen.queryByText('Resubmit to n8n')).not.toBeInTheDocument();
  });

  it('folder row in trash: only Open (no mutating folder actions)', () => {
    renderActions({ item: folderItem, isTrashView: true });
    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.queryByText('New subfolder')).not.toBeInTheDocument();
    expect(screen.queryByText('Delete')).not.toBeInTheDocument();
  });

  it('AC-F2: a file row carries "Set company…" after "Move to…"', () => {
    renderActions({ item: fileItem });
    const labels = screen.getAllByRole('menuitem').map((el) => el.textContent?.trim());
    const moveIndex = labels.findIndex((l) => l === 'Move to…');
    const setCompanyIndex = labels.findIndex((l) => l === 'Set company…');
    expect(moveIndex).toBeGreaterThanOrEqual(0);
    expect(setCompanyIndex).toBe(moveIndex + 1);
  });

  it('AC-F2: a folder row carries "Set company…" after "Move to…"', () => {
    renderActions({ item: folderItem });
    const labels = screen.getAllByRole('menuitem').map((el) => el.textContent?.trim());
    const moveIndex = labels.findIndex((l) => l === 'Move to…');
    const setCompanyIndex = labels.findIndex((l) => l === 'Set company…');
    expect(moveIndex).toBeGreaterThanOrEqual(0);
    expect(setCompanyIndex).toBe(moveIndex + 1);
  });

  it('AC-F2: "Set company…" is absent from a file row in trash', () => {
    renderActions({ item: fileItem, isTrashView: true });
    expect(screen.queryByText('Set company…')).not.toBeInTheDocument();
  });

  it('AC-F2: "Set company…" is absent from a folder row in trash', () => {
    renderActions({ item: folderItem, isTrashView: true });
    expect(screen.queryByText('Set company…')).not.toBeInTheDocument();
  });
});
