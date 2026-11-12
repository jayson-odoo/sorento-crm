'use client';

import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  AttachmentMoveClashError,
  bulkMoveAttachments,
  bulkRestoreAttachments,
  updateAttachment,
  type AttachmentMoveResolution,
  type AttachmentNotMoved,
} from '../../attachments/services/attachmentService';
import { updateDirectory } from '../../attachments/services/directoryService';
import type { MoveOutcome, MoveSkipped } from './driveMoveSummary';

type Action = 'keep' | 'rename' | 'replace' | 'skip';

export type ClashChoice = { kind: 'cancel' } | { kind: Action; name?: string; forAll: boolean };

/** Shown in place of the name box while "Apply to all" is ticked. */
const HINT = 'Rename all adds a number to each name, like (1).';

interface Prompt {
  conflict: Pick<AttachmentNotMoved, 'message' | 'file_name' | 'suggested_name'>;
  index: number;
  total: number;
}

type BulkCall = (
  ids: string[],
  options: { checkOnly?: boolean; resolutions?: Record<string, AttachmentMoveResolution> }
) => Promise<{ updated: number; not_moved: AttachmentNotMoved[]; renamed?: number; replaced?: number }>;

/**
 * FILES-MOVE-DUPLICATE: same-name files are allowed (owner, 12 Nov 17:35), and every action
 * that would put a second file of one name into a folder asks first, Windows-style.
 *
 * 1. One check-only call finds every clash; nothing changes yet.
 * 2. One window walks them ("1 of N"): Keep both (main), Rename (the typed name, this file
 *    only), Replace (the file already there goes to Trash), Skip (leave this file where it is),
 *    with "Apply to all N remaining conflicts" (Keep all / Rename all / Replace all / Skip all).
 *    Cancel, the X and Esc stop the WHOLE action: nothing changes.
 * 3. One call carries every decision; the outcome feeds `summarizeMove`.
 *
 * `moveFiles` (Move to..., drag), `restoreFiles` (Trash) and `askOne` (Rename in a folder)
 * share the window. Render `MoveClashDialog` once.
 */
export function useMoveFiles() {
  const queryClient = useQueryClient();
  const canReplace = useHasPermission('resource.attachments.delete');
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [name, setName] = useState('');
  const [forAll, setForAll] = useState(false);
  const resolverRef = useRef<((choice: ClashChoice) => void) | null>(null);

  const ask = useCallback(
    (next: Prompt) =>
      new Promise<ClashChoice>((resolve) => {
        setPrompt(next);
        setName(next.conflict.suggested_name || next.conflict.file_name);
        setForAll(false);
        resolverRef.current = resolve;
      }),
    []
  );

  const answer = useCallback((choice: ClashChoice) => {
    const resolve = resolverRef.current;
    resolverRef.current = null;
    setPrompt(null);
    // Resolve after the window closes so the next clash opens cleanly.
    setTimeout(() => resolve?.(choice), 0);
  }, []);

  /** One clash on its own (Rename inside a folder): no counter, no tick box. */
  const askOne = useCallback(
    (conflict: Prompt['conflict']) => ask({ conflict, index: 0, total: 1 }),
    [ask]
  );

  const run = useCallback(
    async (
      ids: string[],
      call: BulkCall,
      folders: { id: string; name: string }[],
      moveFolder: (id: string) => Promise<unknown>,
      verb: 'moved' | 'restored' = 'moved'
    ): Promise<MoveOutcome> => {
      const outcome: MoveOutcome = {
        cancelled: false,
        moved: 0,
        renamed: 0,
        replaced: 0,
        skipped: [],
        notMoved: [],
      };
      const resolutions: Record<string, AttachmentMoveResolution> = {};
      const names: Record<string, string> = {};
      const failedAll = (err: unknown) =>
        outcome.notMoved.push({
          name: ids.length === 1 ? 'The file' : `${ids.length} files`,
          reason: err instanceof Error ? err.message : `could not be ${verb}`,
        } satisfies MoveSkipped);

      // 1. Every clash, before anything changes.
      let conflicts: AttachmentNotMoved[] = [];
      if (ids.length > 0) {
        try {
          conflicts = (await call(ids, { checkOnly: true })).not_moved ?? [];
        } catch (err) {
          failedAll(err);
          return outcome;
        }
      }

      // 2. One decision per clash, or one for all of the remaining.
      let applyToRest: Action | null = null;
      for (let i = 0; i < conflicts.length; i += 1) {
        const conflict = conflicts[i];
        names[conflict.attachment_id] = conflict.file_name;
        if (applyToRest) {
          resolutions[conflict.attachment_id] = { action: applyToRest };
          continue;
        }
        const choice = await ask({ conflict, index: i, total: conflicts.length });
        if (choice.kind === 'cancel') return { ...outcome, cancelled: true };
        resolutions[conflict.attachment_id] =
          choice.kind === 'rename' && choice.name && !choice.forAll
            ? { action: 'rename', name: choice.name }
            : { action: choice.kind };
        if (choice.forAll) applyToRest = choice.kind;
      }

      // 3. Folders, then every file in one call.
      const folderResults = await Promise.allSettled(folders.map((folder) => moveFolder(folder.id)));
      folderResults.forEach((r, i) => {
        if (r.status === 'fulfilled') outcome.moved += 1;
        else outcome.notMoved.push({ name: folders[i].name, reason: r.reason instanceof Error ? r.reason.message : '' });
      });
      if (ids.length > 0) {
        try {
          const result = await call(ids, { resolutions });
          const left = new Map((result.not_moved ?? []).map((n) => [n.attachment_id, n]));
          for (const [id, resolution] of Object.entries(resolutions)) {
            if (resolution.action === 'skip') {
              outcome.skipped.push(names[id]);
              left.delete(id);
            }
          }
          // The server counts what it renamed / replaced; Keep both is a plain move.
          outcome.renamed = result.renamed ?? 0;
          outcome.replaced = result.replaced ?? 0;
          outcome.moved += result.updated - outcome.renamed - outcome.replaced;
          left.forEach((n) => outcome.notMoved.push({ name: names[n.attachment_id] ?? n.file_name, reason: n.message }));
        } catch (err) {
          failedAll(err);
        }
      }
      queryClient.invalidateQueries({ queryKey: ['drive-contents'] });
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      if (folders.length > 0) queryClient.invalidateQueries({ queryKey: ['attachment-directories-tree'] });
      return outcome;
    },
    [ask, queryClient]
  );

  const moveFiles = useCallback(
    (fileIds: string[], destinationId: string | null, folders: { id: string; name: string }[] = []) =>
      run(
        fileIds,
        (ids, options) => bulkMoveAttachments(ids, destinationId, options),
        folders,
        (id) => updateDirectory(id, { parent_id: destinationId })
      ),
    [run]
  );

  const restoreFiles = useCallback(
    (fileIds: string[]) =>
      run(fileIds, (ids, options) => bulkRestoreAttachments(ids, options), [], async () => {}, 'restored'),
    [run]
  );

  /**
   * Rename inside a folder. A name already shown there opens the window (no counter):
   * Keep both renames anyway, Rename uses the box (prefilled "name (1)"), Replace sends the
   * other file to Trash, Skip / Cancel leave the name as it was. Resolves to whether it renamed.
   */
  const renameFile = useCallback(
    async (attachmentId: string, newName: string): Promise<boolean> => {
      let name = newName;
      let onConflict: 'keep' | 'rename' | 'replace' | undefined;
      for (;;) {
        try {
          await updateAttachment(attachmentId, { stored_filename: name, ...(onConflict ? { on_conflict: onConflict } : {}) });
          queryClient.invalidateQueries({ queryKey: ['drive-contents'] });
          queryClient.invalidateQueries({ queryKey: ['attachments'] });
          return true;
        } catch (err) {
          if (!(err instanceof AttachmentMoveClashError)) throw err;
          const choice = await askOne({
            message: err.message,
            file_name: err.detail.file_name,
            suggested_name: err.detail.suggested_name,
          });
          if (choice.kind === 'cancel' || choice.kind === 'skip') return false;
          onConflict = choice.kind;
          if (choice.kind === 'rename') name = choice.name || err.detail.suggested_name || name;
        }
      }
    },
    [askOne, queryClient]
  );

  const trimmed = name.trim();
  const remaining = prompt ? prompt.total - prompt.index - 1 : 0;
  const choose = (kind: Action) => answer({ kind, forAll, name: kind === 'rename' && !forAll ? trimmed : undefined });

  const MoveClashDialog = (
    <Dialog open={prompt !== null} onOpenChange={(open) => !open && answer({ kind: 'cancel' })}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          {/* pe-8 keeps a long name clear of the close X in the corner. */}
          <DialogTitle className="line-clamp-2 break-words pe-8" title={prompt?.conflict.message}>
            {prompt?.conflict.message}
          </DialogTitle>
          <DialogDescription>
            {prompt && prompt.total > 1 ? `${prompt.index + 1} of ${prompt.total}` : 'Choose what to do.'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-5 pb-1">
          <div className="space-y-2">
            <Label htmlFor={forAll ? undefined : 'move-clash-name'}>New name</Label>
            {forAll ? (
              // Same height as the box it stands in for, so ticking never moves the layout.
              <p
                className="flex h-8.5 items-center rounded-md border border-dashed px-3 text-sm text-muted-foreground"
                title={HINT}
              >
                <span className="truncate">{HINT}</span>
              </p>
            ) : (
              <Input
                id="move-clash-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && trimmed) {
                    e.preventDefault();
                    choose('rename');
                  }
                }}
              />
            )}
          </div>
          {remaining > 0 && (
            <div className="flex items-center gap-2">
              <Checkbox
                id="move-clash-for-all"
                checked={forAll}
                onCheckedChange={(checked) => setForAll(checked === true)}
              />
              {/* Wording follows the app's existing "Apply to all lines" (dealer-kit TagSizeControl). */}
              <Label htmlFor="move-clash-for-all" className="font-normal">
                {`Apply to all ${remaining} remaining conflict${remaining === 1 ? '' : 's'}`}
              </Label>
            </div>
          )}
        </div>
        <DialogFooter className="flex-col-reverse flex-wrap gap-2 pt-4 sm:flex-row">
          <Button variant="ghost" onClick={() => answer({ kind: 'cancel' })}>
            Cancel
          </Button>
          <Button variant="outline" onClick={() => choose('skip')}>
            {forAll ? 'Skip all' : 'Skip'}
          </Button>
          {canReplace && (
            <Button variant="outline" onClick={() => choose('replace')}>
              {forAll ? 'Replace all' : 'Replace'}
            </Button>
          )}
          <Button variant="outline" onClick={() => choose('rename')} disabled={!forAll && !trimmed}>
            {forAll ? 'Rename all' : 'Rename'}
          </Button>
          <Button onClick={() => choose('keep')}>{forAll ? 'Keep all' : 'Keep both'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { moveFiles, restoreFiles, renameFile, askOne, MoveClashDialog };
}
