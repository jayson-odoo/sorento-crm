/**
 * FILES-MOVE-DUPLICATE: the move flow behind "Move to..." and drag (hand test 12 Nov).
 * Every conflict is found before anything moves; one dialog walks them "1 of N" with
 * "Do this for the remaining" (Windows-style); Cancel / X / Esc cancel the whole move.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const bulkMoveAttachments = vi.fn();
const updateDirectory = vi.fn();
let canDelete = true;

vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => canDelete }));
vi.mock('../../attachments/services/attachmentService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../attachments/services/attachmentService')>();
  return { ...actual, bulkMoveAttachments: (...args: unknown[]) => bulkMoveAttachments(...args) };
});
vi.mock('../../attachments/services/directoryService', () => ({
  updateDirectory: (...args: unknown[]) => updateDirectory(...args),
}));

import { useMoveFiles } from './useMoveFiles';
import type { MoveOutcome } from './driveMoveSummary';

function conflict(i: number) {
  return {
    attachment_id: `f-${i}`,
    file_name: `scan ${i}.pdf`,
    folder_name: 'Folder B',
    message: `scan ${i}.pdf already exists in Folder B.`,
    existing_file_name: `scan ${i}.pdf`,
    suggested_name: `scan ${i} (1).pdf`,
  };
}

type Handle = {
  move: (ids: string[], dest: string | null, folders?: { id: string; name: string }[]) => Promise<MoveOutcome>;
};

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

/** First call = the check-only preflight, second = the move itself. */
function preflight(
  conflicts: ReturnType<typeof conflict>[],
  execute: { updated: number; not_moved: unknown[]; renamed?: number; replaced?: number } = { updated: 0, not_moved: [] }
) {
  bulkMoveAttachments.mockImplementation(async (_ids: string[], _dest: string, opts?: { checkOnly?: boolean }) =>
    opts?.checkOnly ? { updated: 0, not_moved: conflicts } : execute
  );
}

describe('useMoveFiles', () => {
  beforeEach(() => {
    bulkMoveAttachments.mockReset();
    updateDirectory.mockReset();
    canDelete = true;
  });

  it('no conflict: checks first, then moves everything in one call, no dialog', async () => {
    preflight([], { updated: 3, not_moved: [] });
    const outcome = await mount().move(['a', 'b', 'c'], 'dir-b');
    expect(bulkMoveAttachments).toHaveBeenNthCalledWith(1, ['a', 'b', 'c'], 'dir-b', { checkOnly: true });
    expect(bulkMoveAttachments).toHaveBeenNthCalledWith(2, ['a', 'b', 'c'], 'dir-b', { resolutions: {} });
    expect(outcome).toMatchObject({ cancelled: false, moved: 3, renamed: 0, replaced: 0 });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('100 files, 100 conflicts: one decision with "Do this for the remaining" renames all', async () => {
    const conflicts = Array.from({ length: 100 }, (_, i) => conflict(i));
    const ids = conflicts.map((c) => c.attachment_id);
    preflight(conflicts, { updated: 100, renamed: 100, not_moved: [] });
    const pending = mount().move(ids, 'dir-b');
    expect(await screen.findByText('1 of 100')).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Apply to all 99 remaining conflicts' }));
    // Ticked: the name row stays in place with a plain hint instead of the box (no jump).
    expect(screen.queryByRole('textbox', { name: 'New name' })).toBeNull();
    expect(screen.getByText('Each file keeps its own name with (1) added.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Rename' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Skip all' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Replace all' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Keep both' }));
    const outcome = await pending;
    const [, , opts] = bulkMoveAttachments.mock.calls[1];
    expect(Object.keys(opts.resolutions)).toHaveLength(100);
    expect(opts.resolutions['f-0']).toEqual({ action: 'rename' });
    expect(opts.resolutions['f-99']).toEqual({ action: 'rename' });
    expect(bulkMoveAttachments).toHaveBeenCalledTimes(2);
    expect(outcome).toMatchObject({ cancelled: false, moved: 0, renamed: 100 });
  });

  it('without the tick box each conflict is asked; the typed name goes with that file only', async () => {
    preflight([conflict(1), conflict(2)], { updated: 1, renamed: 1, not_moved: [conflict(2)] });
    const pending = mount().move(['f-1', 'f-2'], 'dir-b');
    expect(await screen.findByText('1 of 2')).toBeTruthy();
    fireEvent.change(screen.getByRole('textbox', { name: 'New name' }), { target: { value: 'mine.pdf' } });
    fireEvent.click(screen.getByRole('button', { name: 'Rename' }));
    expect(await screen.findByText('2 of 2')).toBeTruthy();
    expect(screen.getByDisplayValue('scan 2 (1).pdf')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    const outcome = await pending;
    expect(bulkMoveAttachments.mock.calls[1][2]).toEqual({
      resolutions: { 'f-1': { action: 'rename', name: 'mine.pdf' }, 'f-2': { action: 'skip' } },
    });
    expect(outcome).toMatchObject({ renamed: 1, moved: 0, skipped: ['scan 2.pdf'], notMoved: [] });
  });

  it('Replace for all sends replace for every conflict', async () => {
    preflight([conflict(1), conflict(2), conflict(3)], { updated: 4, replaced: 3, not_moved: [] });
    const pending = mount().move(['plain', 'f-1', 'f-2', 'f-3'], 'dir-b');
    fireEvent.click(await screen.findByRole('checkbox', { name: 'Apply to all 2 remaining conflicts' }));
    fireEvent.click(screen.getByRole('button', { name: 'Replace all' }));
    const outcome = await pending;
    expect(bulkMoveAttachments.mock.calls[1][2].resolutions).toEqual({
      'f-1': { action: 'replace' },
      'f-2': { action: 'replace' },
      'f-3': { action: 'replace' },
    });
    expect(outcome).toMatchObject({ moved: 1, replaced: 3 });
  });

  it('Cancel cancels the whole move: nothing moves, folders included', async () => {
    preflight([conflict(1)]);
    const pending = mount().move(['plain', 'f-1'], 'dir-b', [{ id: 'd-1', name: 'Specs' }]);
    expect(await screen.findByText('scan 1.pdf already exists in Folder B.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    const outcome = await pending;
    expect(outcome.cancelled).toBe(true);
    expect(bulkMoveAttachments).toHaveBeenCalledTimes(1); // the check only
    expect(updateDirectory).not.toHaveBeenCalled();
  });

  it('Esc (closing the window) also cancels the whole move', async () => {
    preflight([conflict(1), conflict(2)]);
    const pending = mount().move(['f-1', 'f-2'], 'dir-b');
    const dialog = await screen.findByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(async () => expect((await pending).cancelled).toBe(true));
    expect(bulkMoveAttachments).toHaveBeenCalledTimes(1);
  });

  it('one conflict shows no "1 of" counter and no tick box', async () => {
    preflight([conflict(1)], { updated: 1, renamed: 1, not_moved: [] });
    const pending = mount().move(['f-1'], 'dir-b');
    await screen.findByText('scan 1.pdf already exists in Folder B.');
    expect(screen.queryByText('1 of 1')).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Rename' }));
    expect((await pending).renamed).toBe(1);
  });

  it('Replace is not offered without the permission to delete files', async () => {
    canDelete = false;
    preflight([conflict(1)], { updated: 0, not_moved: [conflict(1)] });
    const pending = mount().move(['f-1'], 'dir-b');
    await screen.findByRole('button', { name: 'Skip' });
    expect(screen.queryByRole('button', { name: 'Replace' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    expect((await pending).skipped).toEqual(['scan 1.pdf']);
  });

  it('a file the server still refused is named with its reason', async () => {
    preflight([conflict(1)], {
      updated: 0,
      not_moved: [{ ...conflict(1), message: 'You cannot change that file.' }],
    });
    const pending = mount().move(['f-1'], 'dir-b');
    fireEvent.click(await screen.findByRole('button', { name: 'Replace' }));
    const outcome = await pending;
    expect(outcome.replaced).toBe(0);
    expect(outcome.notMoved).toEqual([{ name: 'scan 1.pdf', reason: 'You cannot change that file.' }]);
  });

  it('folders move after the decisions; a refused folder is named', async () => {
    preflight([], { updated: 2, not_moved: [] });
    updateDirectory.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('Cannot move a folder into itself'));
    const outcome = await mount().move(['a', 'b'], 'dir-b', [
      { id: 'd-1', name: 'Specs' },
      { id: 'd-2', name: 'Drafts' },
    ]);
    expect(outcome.moved).toBe(3);
    expect(outcome.notMoved).toEqual([{ name: 'Drafts', reason: 'Cannot move a folder into itself' }]);
  });

  it('a resolved file whose clash vanished counts as a plain move (server counts)', async () => {
    preflight([conflict(1)], { updated: 1, renamed: 0, replaced: 0, not_moved: [] });
    const pending = mount().move(['f-1'], 'dir-b');
    fireEvent.click(await screen.findByRole('button', { name: 'Rename' }));
    expect(await pending).toMatchObject({ moved: 1, renamed: 0, replaced: 0 });
  });

  it('unticked, the buttons read Rename / Skip / Replace; one remaining conflict reads singular', async () => {
    preflight([conflict(1), conflict(2)], { updated: 2, renamed: 2, not_moved: [] });
    const pending = mount().move(['f-1', 'f-2'], 'dir-b');
    expect(await screen.findByRole('checkbox', { name: 'Apply to all 1 remaining conflict' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Rename' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Skip' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Replace' })).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Apply to all 1 remaining conflict' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Apply to all 1 remaining conflict' }));
    // Unticking brings the editable box back with the suggestion.
    expect(screen.getByDisplayValue('scan 1 (1).pdf')).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Apply to all 1 remaining conflict' }));
    fireEvent.click(screen.getByRole('button', { name: 'Keep both' }));
    expect(await pending).toMatchObject({ renamed: 2 });
  });
});
