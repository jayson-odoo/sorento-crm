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
  bulkMoveAttachments,
  type AttachmentMoveResolution,
  type AttachmentNotMoved,
} from '../../attachments/services/attachmentService';
import { updateDirectory } from '../../attachments/services/directoryService';
import type { MoveOutcome, MoveSkipped } from './driveMoveSummary';

type Action = 'skip' | 'replace' | 'rename';

/** Shown in place of the name box under "Apply to all": the server adds (1), or (2) if taken. */
const HINT = 'Each file gets a number added, like (1).';
type Choice = { kind: 'cancel' } | { kind: Action; name?: string; forAll: boolean };

interface Prompt {
  conflict: AttachmentNotMoved;
  index: number;
  total: number;
}

/**
 * FILES-MOVE-DUPLICATE: move files (and folders) into a folder, Windows-style.
 *
 * 1. One check-only call finds every name conflict; nothing moves yet.
 * 2. One window walks the conflicts ("1 of N"): Rename (keeps both; the typed name is for
 *    this file only), Replace (the file already there goes to Trash) or Skip, with "Do this
 *    for the remaining N-1 conflicts" so 100 conflicts take one decision. Cancel, the X and
 *    Esc cancel the WHOLE move: nothing is moved, files without a conflict included.
 * 3. One call moves everything with the decisions; the outcome feeds `summarizeMove`.
 *
 *   const { moveFiles, MoveClashDialog } = useMoveFiles();
 *   const outcome = await moveFiles(fileIds, destinationId, folders);
 *   // render {MoveClashDialog} once
 */
export function useMoveFiles() {
  const queryClient = useQueryClient();
  const canReplace = useHasPermission('resource.attachments.delete');
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [name, setName] = useState('');
  const [forAll, setForAll] = useState(false);
  const resolverRef = useRef<((choice: Choice) => void) | null>(null);

  const ask = useCallback(
    (next: Prompt) =>
      new Promise<Choice>((resolve) => {
        setPrompt(next);
        setName(next.conflict.suggested_name || next.conflict.file_name);
        setForAll(false);
        resolverRef.current = resolve;
      }),
    []
  );

  const answer = useCallback((choice: Choice) => {
    const resolve = resolverRef.current;
    resolverRef.current = null;
    setPrompt(null);
    // Resolve after the window closes so the next conflict opens cleanly.
    setTimeout(() => resolve?.(choice), 0);
  }, []);

  const moveFiles = useCallback(
    async (
      fileIds: string[],
      destinationId: string | null,
      folders: { id: string; name: string }[] = []
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

      // 1. Every conflict, before anything moves.
      let conflicts: AttachmentNotMoved[] = [];
      if (fileIds.length > 0) {
        try {
          conflicts = (await bulkMoveAttachments(fileIds, destinationId, { checkOnly: true })).not_moved ?? [];
        } catch (err) {
          outcome.notMoved.push({
            name: fileIds.length === 1 ? 'The file' : `${fileIds.length} files`,
            reason: err instanceof Error ? err.message : 'could not be moved',
          });
          return outcome;
        }
      }

      // 2. One decision per conflict, or one for all of the remaining.
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
      const folderResults = await Promise.allSettled(
        folders.map((folder) => updateDirectory(folder.id, { parent_id: destinationId }))
      );
      folderResults.forEach((r, i) => {
        if (r.status === 'fulfilled') outcome.moved += 1;
        else
          outcome.notMoved.push({
            name: folders[i].name,
            reason: r.reason instanceof Error ? r.reason.message : '',
          });
      });
      if (fileIds.length > 0) {
        try {
          const result = await bulkMoveAttachments(fileIds, destinationId, { resolutions });
          const left = new Map((result.not_moved ?? []).map((n) => [n.attachment_id, n]));
          for (const [id, resolution] of Object.entries(resolutions)) {
            if (resolution.action === 'skip') {
              outcome.skipped.push(names[id]);
              left.delete(id);
            }
          }
          // The server counts what it renamed / replaced: a clash that vanished before the move
          // makes a plain move, never a phantom "renamed".
          outcome.renamed = result.renamed ?? 0;
          outcome.replaced = result.replaced ?? 0;
          outcome.moved += result.updated - outcome.renamed - outcome.replaced;
          left.forEach((n) =>
            outcome.notMoved.push({ name: names[n.attachment_id] ?? n.file_name, reason: n.message })
          );
        } catch (err) {
          outcome.notMoved.push({
            name: fileIds.length === 1 ? 'The file' : `${fileIds.length} files`,
            reason: err instanceof Error ? err.message : 'could not be moved',
          } satisfies MoveSkipped);
        }
      }
      if (folders.length > 0) {
        queryClient.invalidateQueries({ queryKey: ['attachment-directories-tree'] });
      }
      queryClient.invalidateQueries({ queryKey: ['drive-contents'] });
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      return outcome;
    },
    [ask, queryClient]
  );

  const trimmed = name.trim();
  const remaining = prompt ? prompt.total - prompt.index - 1 : 0;
  const choose = (kind: Action) =>
    answer({ kind, forAll, name: kind === 'rename' && !forAll ? trimmed : undefined });

  const MoveClashDialog = (
    <Dialog open={prompt !== null} onOpenChange={(open) => !open && answer({ kind: 'cancel' })}>
      <DialogContent className="sm:max-w-md">
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
        <DialogFooter className="flex-col-reverse gap-2 pt-4 sm:flex-row">
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
          <Button onClick={() => choose('rename')} disabled={!forAll && !trimmed}>
            {forAll ? 'Rename all' : 'Rename'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { moveFiles, MoveClashDialog };
}
