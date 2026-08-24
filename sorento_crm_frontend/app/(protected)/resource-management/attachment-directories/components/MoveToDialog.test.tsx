/**
 * MoveToDialog - universal non-drag move path (UAC E5) + cycle-guard target
 * disabling (toward E4).
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import MoveToDialog from './MoveToDialog';
import { useDirectoryTree } from '../../attachments/hooks/useAttachments';

vi.mock('../../attachments/hooks/useAttachments', () => ({
  useDirectoryTree: vi.fn(),
}));
const mockedTree = vi.mocked(useDirectoryTree);

const tree = [
  {
    id: 'mkt',
    name: 'Marketing',
    parent_id: null,
    sort_order: 0,
    created_at: '',
    children: [
      { id: 'camp', name: 'Campaigns', parent_id: 'mkt', sort_order: 0, created_at: '', children: [] },
    ],
  },
  { id: 'fin', name: 'Finance', parent_id: null, sort_order: 1, created_at: '', children: [] },
];

function setup(selection = { fileIds: ['f1'], folderIds: [] as string[] }) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  mockedTree.mockReturnValue({ data: tree } as any);
  const onMove = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <MoveToDialog
      open
      onOpenChange={onOpenChange}
      selection={selection}
      onMove={onMove}
    />
  );
  return { onMove, onOpenChange };
}

describe('MoveToDialog', () => {
  it('E5: lists the folder tree and the root option', () => {
    setup();
    expect(screen.getByText('All files (root)')).toBeInTheDocument();
    expect(screen.getByText('Marketing')).toBeInTheDocument();
    expect(screen.getByText('Finance')).toBeInTheDocument();
  });

  it('E5: selecting a destination then "Move here" calls onMove with that id', () => {
    const { onMove } = setup();
    fireEvent.click(screen.getByText('Finance'));
    fireEvent.click(screen.getByRole('button', { name: /move here/i }));
    expect(onMove).toHaveBeenCalledWith('fin');
  });

  it('E5: defaults to root (null) when no folder is picked', () => {
    const { onMove } = setup();
    fireEvent.click(screen.getByRole('button', { name: /move here/i }));
    expect(onMove).toHaveBeenCalledWith(null);
  });

  it('E4 guard: a folder being moved is not selectable as its own destination', () => {
    const { onMove } = setup({ fileIds: [], folderIds: ['mkt'] });
    // Clicking the moved folder must NOT set it as the target.
    fireEvent.click(screen.getByText('Marketing'));
    fireEvent.click(screen.getByRole('button', { name: /move here/i }));
    // target stayed null (root) - Marketing was blocked.
    expect(onMove).toHaveBeenCalledWith(null);
  });

  it('shows the selection count in the title', () => {
    setup({ fileIds: ['f1', 'f2'], folderIds: ['x'] });
    expect(screen.getByText(/move 3 items/i)).toBeInTheDocument();
  });
});
