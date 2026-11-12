/**
 * FILES-MOVE-DUPLICATE: same-name files are allowed (owner, 12 Nov 17:35), and every clash
 * is asked first. One window, Windows-style: "1 of N", Keep both (main) / Rename / Replace /
 * Skip, "Apply to all N remaining conflicts" (Keep all / Rename all / Replace all / Skip all),
 * Cancel / X / Esc stop the whole action. Move, drag and restore share it; Rename asks one.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const bulkMoveAttachments = vi.fn();
const bulkRestoreAttachments = vi.fn();
const updateDirectory = vi.fn();
let canDelete = true;

vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => canDelete }));
vi.mock('../../attachments/services/attachmentService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../attachments/services/attachmentService')>();
  return {
    ...actual,
    bulkMoveAttachments: (...args: unknown[]) => bulkMoveAttachments(...args),
    bulkRestoreAttachments: (...args: unknown[]) => bulkRestoreAttachments(...args),
  };
});
vi.mock('../../attachments/services/directoryService', () => ({
  updateDirectory: (...args: unknown[]) => updateDirectory(...args),
}));

import { useMoveFiles, type ClashChoice } from './useMoveFiles';
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

type Handle = ReturnType<typeof useMoveFiles>;

function Harness({ refObj }: { refObj: { current: Handle | null } }) {
  const hook = useMoveFiles();
  refObj.current = hook;
  return <div>{hook.MoveClashDialog}</div>;
}

function mount(): Handle {
  const refObj: { current: Handle | null } = { current: null };
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Harness refObj={refObj} />
    </QueryClientProvider>
  );
  return refObj.current!;
}

type Execute = { updated: number; not_moved: unknown[]; renamed?: number; replaced?: number };

/** First call = the check-only pass, second = the action itself. */
function preflight(fn: ReturnType<typeof vi.fn>, conflicts: ReturnType<typeof conflict>[], execute: Execute = { updated: 0, not_moved: [] }) {
  fn.mockImplementation(async (_ids: string[], ...rest: unknown[]) => {
    const opts = rest[rest.length - 1] as { checkOnly?: boolean } | undefined;
    return opts?.checkOnly ? { updated: 0, not_moved: conflicts } : execute;
  });
}

const button = (name: string) => screen.getByRole('button', { name });

describe('useMoveFiles', () => {
  beforeEach(() => {
    bulkMoveAttachments.mockReset();
    bulkRestoreAttachments.mockReset();
    updateDirectory.mockReset();
    canDelete = true;
  });

  it('no conflict: checks first, then moves everything in one call, no window', async () => {
    preflight(bulkMoveAttachments, [], { updated: 3, not_moved: [] });
    const outcome = await mount().moveFiles(['a', 'b', 'c'], 'dir-b');
    expect(bulkMoveAttachments).toHaveBeenNthCalledWith(1, ['a', 'b', 'c'], 'dir-b', { checkOnly: true });
    expect(bulkMoveAttachments).toHaveBeenNthCalledWith(2, ['a', 'b', 'c'], 'dir-b', { resolutions: {} });
    expect(outcome).toMatchObject({ cancelled: false, moved: 3 });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('unticked: Keep both is the main button, beside Rename, Replace, Skip and Cancel', async () => {
    preflight(bulkMoveAttachments, [conflict(1), conflict(2)], { updated: 2, not_moved: [] });
    const pending = mount().moveFiles(['f-1', 'f-2'], 'dir-b');
    expect(await screen.findByText('1 of 2')).toBeTruthy();
    for (const name of ['Cancel', 'Skip', 'Replace', 'Rename', 'Keep both']) expect(button(name)).toBeTruthy();
    expect(screen.getByRole('textbox', { name: 'New name' })).toHaveProperty('value', 'scan 1 (1).pdf');
    fireEvent.click(button('Keep both'));
    expect(await screen.findByText('2 of 2')).toBeTruthy();
    fireEvent.change(screen.getByRole('textbox', { name: 'New name' }), { target: { value: 'mine.pdf' } });
    fireEvent.click(button('Rename'));
    await pending;
    expect(bulkMoveAttachments.mock.calls[1][2]).toEqual({
      resolutions: { 'f-1': { action: 'keep' }, 'f-2': { action: 'rename', name: 'mine.pdf' } },
    });
  });

  it('100 conflicts take one decision: tick "Apply to all", then Keep all', async () => {
    const conflicts = Array.from({ length: 100 }, (_, i) => conflict(i));
    preflight(bulkMoveAttachments, conflicts, { updated: 100, not_moved: [] });
    const pending = mount().moveFiles(conflicts.map((c) => c.attachment_id), 'dir-b');
    expect(await screen.findByText('1 of 100')).toBeTruthy();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Apply to all 99 remaining conflicts' }));
    for (const name of ['Cancel', 'Skip all', 'Replace all', 'Rename all', 'Keep all']) expect(button(name)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Keep both' })).toBeNull();
    // The name row stays (no jump) with a hint instead of the box.
    expect(screen.queryByRole('textbox', { name: 'New name' })).toBeNull();
    expect(screen.getByText('Rename all adds a number to each name, like (1).')).toBeTruthy();
    fireEvent.click(button('Keep all'));
    const outcome = await pending;
    const { resolutions } = bulkMoveAttachments.mock.calls[1][2];
    expect(Object.keys(resolutions)).toHaveLength(100);
    expect(new Set(Object.values(resolutions).map((r) => JSON.stringify(r)))).toEqual(new Set(['{"action":"keep"}']));
    expect(bulkMoveAttachments).toHaveBeenCalledTimes(2);
    expect(outcome).toMatchObject({ moved: 100 });
  });

  it('Rename all, Replace all and Skip all send that answer for every conflict', async () => {
    for (const [label, action] of [
      ['Rename all', 'rename'],
      ['Replace all', 'replace'],
      ['Skip all', 'skip'],
    ] as const) {
      bulkMoveAttachments.mockReset();
      preflight(bulkMoveAttachments, [conflict(1), conflict(2)], { updated: 2, not_moved: [] });
      const hook = mount();
      const pending = hook.moveFiles(['f-1', 'f-2'], 'dir-b');
      fireEvent.click(await screen.findByRole('checkbox', { name: 'Apply to all 1 remaining conflict' }));
      fireEvent.click(button(label));
      await pending;
      expect(bulkMoveAttachments.mock.calls[1][2].resolutions).toEqual({
        'f-1': { action },
        'f-2': { action },
      });
      document.body.innerHTML = '';
    }
  });

  it('Cancel stops the whole move: no move call, folders untouched', async () => {
    preflight(bulkMoveAttachments, [conflict(1)]);
    const pending = mount().moveFiles(['plain', 'f-1'], 'dir-b', [{ id: 'd-1', name: 'Specs' }]);
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    expect((await pending).cancelled).toBe(true);
    expect(bulkMoveAttachments).toHaveBeenCalledTimes(1);
    expect(updateDirectory).not.toHaveBeenCalled();
  });

  it('Esc also cancels the whole move', async () => {
    preflight(bulkMoveAttachments, [conflict(1), conflict(2)]);
    const pending = mount().moveFiles(['f-1', 'f-2'], 'dir-b');
    fireEvent.keyDown(await screen.findByRole('dialog'), { key: 'Escape' });
    await waitFor(async () => expect((await pending).cancelled).toBe(true));
    expect(bulkMoveAttachments).toHaveBeenCalledTimes(1);
  });

  it('one conflict: no counter and no tick box', async () => {
    preflight(bulkMoveAttachments, [conflict(1)], { updated: 1, not_moved: [] });
    const pending = mount().moveFiles(['f-1'], 'dir-b');
    await screen.findByText('scan 1.pdf already exists in Folder B.');
    expect(screen.queryByText('1 of 1')).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.click(button('Keep both'));
    await pending;
  });

  it('Replace is not offered without the permission to delete files', async () => {
    canDelete = false;
    preflight(bulkMoveAttachments, [conflict(1)], { updated: 0, not_moved: [conflict(1)] });
    const pending = mount().moveFiles(['f-1'], 'dir-b');
    await screen.findByRole('button', { name: 'Skip' });
    expect(screen.queryByRole('button', { name: 'Replace' })).toBeNull();
    fireEvent.click(button('Skip'));
    expect((await pending).skipped).toEqual(['scan 1.pdf']);
  });

  it('server counts and refusals feed the summary', async () => {
    preflight(bulkMoveAttachments, [conflict(1), conflict(2)], {
      updated: 2,
      renamed: 1,
      replaced: 0,
      not_moved: [{ ...conflict(2), message: 'You cannot change that file.' }],
    });
    const pending = mount().moveFiles(['plain', 'f-1', 'f-2'], 'dir-b');
    fireEvent.click(await screen.findByRole('button', { name: 'Rename' }));
    await screen.findByText('2 of 2');
    fireEvent.click(screen.getByRole('button', { name: 'Replace' }));
    const outcome = await pending;
    expect(outcome).toMatchObject({ moved: 1, renamed: 1, replaced: 0 });
    expect(outcome.notMoved).toEqual([{ name: 'scan 2.pdf', reason: 'You cannot change that file.' }]);
  });

  it('folders move after the decisions; a refused folder is named', async () => {
    preflight(bulkMoveAttachments, [], { updated: 2, not_moved: [] });
    updateDirectory.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('Cannot move a folder into itself'));
    const outcome = await mount().moveFiles(['a', 'b'], 'dir-b', [
      { id: 'd-1', name: 'Specs' },
      { id: 'd-2', name: 'Drafts' },
    ]);
    expect(outcome.moved).toBe(3);
    expect(outcome.notMoved).toEqual([{ name: 'Drafts', reason: 'Cannot move a folder into itself' }]);
  });

  it('restore from Trash: same check-first window, one restore call', async () => {
    preflight(bulkRestoreAttachments, [conflict(1)], { updated: 2, not_moved: [] });
    const pending = mount().restoreFiles(['f-1', 'free']);
    fireEvent.click(await screen.findByRole('button', { name: 'Keep both' }));
    const outcome = await pending;
    expect(bulkRestoreAttachments).toHaveBeenNthCalledWith(1, ['f-1', 'free'], { checkOnly: true });
    expect(bulkRestoreAttachments).toHaveBeenNthCalledWith(2, ['f-1', 'free'], {
      resolutions: { 'f-1': { action: 'keep' } },
    });
    expect(outcome).toMatchObject({ cancelled: false, moved: 2 });
  });

  it('askOne: a single clash (Rename in a folder) gets the same window without counter', async () => {
    const hook = mount();
    const pending: Promise<ClashChoice> = hook.askOne(conflict(1));
    await screen.findByText('scan 1.pdf already exists in Folder B.');
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.click(button('Keep both'));
    expect(await pending).toEqual({ kind: 'keep', forAll: false });
  });
});
