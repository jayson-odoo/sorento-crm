/**
 * FILES-MOVE-DUPLICATE: the move flow behind "Move to..." and drag. The others move; a name
 * clash asks Rename / Replace / Skip; every file left behind is named.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const bulkMoveAttachments = vi.fn();
const updateAttachment = vi.fn();
let canDelete = true;

vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => canDelete }));
vi.mock('../../attachments/services/attachmentService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../attachments/services/attachmentService')>();
  return {
    ...actual,
    bulkMoveAttachments: (...args: unknown[]) => bulkMoveAttachments(...args),
    updateAttachment: (...args: unknown[]) => updateAttachment(...args),
  };
});

import { useMoveFiles } from './useMoveFiles';
import { AttachmentMoveClashError } from '../../attachments/services/attachmentService';
import { summarizeMove, type MoveOutcome } from './driveMoveSummary';

const CLASH = {
  attachment_id: 'f-2',
  file_name: 'photo.jpg',
  folder_name: 'Folder B',
  message: 'photo.jpg already exists in Folder B.',
  existing_file_name: 'photo.jpg',
  suggested_name: 'photo (1).jpg',
};

type Handle = { move: (ids: string[], dest: string | null) => Promise<MoveOutcome> };

function Harness({ refObj }: { refObj: { current: Handle | null } }) {
  const { moveFiles, MoveClashDialog } = useMoveFiles();
  refObj.current = { move: moveFiles };
  return <div>{MoveClashDialog}</div>;
}

function mount() {
  const refObj: { current: Handle | null } = { current: null };
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Harness refObj={refObj} />
    </QueryClientProvider>
  );
  return refObj.current!;
}

describe('useMoveFiles', () => {
  beforeEach(() => {
    bulkMoveAttachments.mockReset();
    updateAttachment.mockReset();
    canDelete = true;
  });

  it('no clash: everything moves in one call, no dialog', async () => {
    bulkMoveAttachments.mockResolvedValue({ updated: 3, not_moved: [] });
    const outcome = await mount().move(['a', 'b', 'c'], 'dir-b');
    expect(bulkMoveAttachments).toHaveBeenCalledWith(['a', 'b', 'c'], 'dir-b');
    expect(outcome).toEqual({ moved: 3, notMoved: [] });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('Skip: the others moved and the skipped file is named in the summary', async () => {
    bulkMoveAttachments.mockResolvedValue({ updated: 2, not_moved: [CLASH] });
    const pending = mount().move(['a', 'f-2', 'c'], 'dir-b');
    fireEvent.click(await screen.findByRole('button', { name: 'Skip' }));
    const outcome = await pending;
    expect(updateAttachment).not.toHaveBeenCalled();
    expect(summarizeMove(outcome).text).toBe(
      '2 moved. 1 not moved: photo.jpg already exists in Folder B.'
    );
  });

  it('Rename: moves under the suggested name, prefilled', async () => {
    bulkMoveAttachments.mockResolvedValue({ updated: 0, not_moved: [CLASH] });
    updateAttachment.mockResolvedValue({});
    const pending = mount().move(['f-2'], 'dir-b');
    expect(await screen.findByDisplayValue('photo (1).jpg')).toBeTruthy();
    expect(screen.getByText('photo.jpg already exists in Folder B.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Rename' }));
    const outcome = await pending;
    expect(updateAttachment).toHaveBeenCalledWith('f-2', {
      directory_id: 'dir-b',
      on_conflict: 'rename',
      stored_filename: 'photo (1).jpg',
    });
    expect(outcome).toEqual({ moved: 1, notMoved: [] });
  });

  it('Rename to a name that is also taken asks again with the new reason', async () => {
    bulkMoveAttachments.mockResolvedValue({ updated: 0, not_moved: [CLASH] });
    updateAttachment
      .mockRejectedValueOnce(
        new AttachmentMoveClashError('taken.jpg already exists in Folder B.', {
          file_name: 'taken.jpg',
          folder_name: 'Folder B',
          existing_file_name: 'taken.jpg',
          suggested_name: 'taken (1).jpg',
        })
      )
      .mockResolvedValueOnce({});
    const pending = mount().move(['f-2'], 'dir-b');
    const input = await screen.findByDisplayValue('photo (1).jpg');
    fireEvent.change(input, { target: { value: 'taken.jpg' } });
    fireEvent.click(screen.getByRole('button', { name: 'Rename' }));
    expect(await screen.findByText('taken.jpg already exists in Folder B.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Rename' }));
    const outcome = await pending;
    expect(updateAttachment).toHaveBeenLastCalledWith('f-2', {
      directory_id: 'dir-b',
      on_conflict: 'rename',
      stored_filename: 'taken (1).jpg',
    });
    expect(outcome.moved).toBe(1);
  });

  it('Replace: sends on_conflict replace', async () => {
    bulkMoveAttachments.mockResolvedValue({ updated: 0, not_moved: [CLASH] });
    updateAttachment.mockResolvedValue({});
    const pending = mount().move(['f-2'], 'dir-b');
    fireEvent.click(await screen.findByRole('button', { name: 'Replace' }));
    await pending;
    expect(updateAttachment).toHaveBeenCalledWith('f-2', {
      directory_id: 'dir-b',
      on_conflict: 'replace',
    });
  });

  it('Replace is not offered without the permission to delete files', async () => {
    canDelete = false;
    bulkMoveAttachments.mockResolvedValue({ updated: 0, not_moved: [CLASH] });
    const pending = mount().move(['f-2'], 'dir-b');
    await screen.findByRole('button', { name: 'Skip' });
    expect(screen.queryByRole('button', { name: 'Replace' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    await waitFor(async () => expect((await pending).notMoved).toHaveLength(1));
  });
});
