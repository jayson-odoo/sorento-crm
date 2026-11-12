'use client';

import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
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
  updateAttachment,
  type AttachmentNotMoved,
} from '../../attachments/services/attachmentService';
import { updateDirectory } from '../../attachments/services/directoryService';
import type { MoveOutcome, MoveSkipped } from './driveMoveSummary';

type Choice = { kind: 'skip' } | { kind: 'replace' } | { kind: 'rename'; name: string };

/**
 * FILES-MOVE-DUPLICATE: move files into a folder; one name clash never stops the rest.
 *
 * Every file that can move does (one bulk-move call). For each one the folder already holds
 * a file of the same name, a dialog asks: Rename (moves under a new name; the stored file and
 * its links are untouched), Replace (the file already there goes to Trash) or Skip. The
 * outcome feeds `summarizeMove` for the one notice.
 *
 *   const { moveFiles, MoveClashDialog } = useMoveFiles();
 *   const outcome = await moveFiles(fileIds, destinationId);
 *   // render {MoveClashDialog} once
 */
export function useMoveFiles() {
  const queryClient = useQueryClient();
  const canReplace = useHasPermission('resource.attachments.delete');
  const [clash, setClash] = useState<AttachmentNotMoved | null>(null);
  const [name, setName] = useState('');
  const resolverRef = useRef<((choice: Choice) => void) | null>(null);

  const ask = useCallback(
    (entry: AttachmentNotMoved) =>
      new Promise<Choice>((resolve) => {
        setClash(entry);
        setName(entry.suggested_name || entry.file_name);
        resolverRef.current = resolve;
      }),
    []
  );

  const answer = useCallback((choice: Choice) => {
    const resolve = resolverRef.current;
    resolverRef.current = null;
    setClash(null);
    // Resolve after the dialog closes so the next file's prompt opens cleanly.
    setTimeout(() => resolve?.(choice), 0);
  }, []);

  const resolveOne = useCallback(
    async (entry: AttachmentNotMoved, destinationId: string | null): Promise<MoveSkipped | null> => {
      let current = entry;
      for (;;) {
        const choice = await ask(current);
        // Skipped: named as the file is, with the clash it was first moved into.
        if (choice.kind === 'skip') return { name: entry.file_name, reason: entry.message };
        try {
          await updateAttachment(
            current.attachment_id,
            choice.kind === 'replace'
              ? { directory_id: destinationId, on_conflict: 'replace' }
              : { directory_id: destinationId, on_conflict: 'rename', stored_filename: choice.name }
          );
          return null;
        } catch (err) {
          if (err instanceof AttachmentMoveClashError) {
            // The new name is taken too: ask again with the fresh reason and suggestion.
            current = { ...current, ...err.detail, message: err.message };
            continue;
          }
          return {
            name: entry.file_name,
            reason: err instanceof Error ? err.message : 'could not be moved',
          };
        }
      }
    },
    [ask]
  );

  const moveFiles = useCallback(
    async (
      fileIds: string[],
      destinationId: string | null,
      folders: { id: string; name: string }[] = []
    ): Promise<MoveOutcome> => {
      let moved = 0;
      const notMoved: MoveSkipped[] = [];
      // Folders: each on its own, so one refusal (e.g. into its own subfolder) names that folder.
      const folderResults = await Promise.allSettled(
        folders.map((folder) => updateDirectory(folder.id, { parent_id: destinationId }))
      );
      folderResults.forEach((r, i) => {
        if (r.status === 'fulfilled') moved += 1;
        else
          notMoved.push({
            name: folders[i].name,
            reason: r.reason instanceof Error ? r.reason.message : '',
          });
      });
      if (fileIds.length > 0) {
        try {
          const result = await bulkMoveAttachments(fileIds, destinationId);
          moved += result.updated;
          for (const entry of result.not_moved ?? []) {
            const skipped = await resolveOne(entry, destinationId);
            if (skipped) notMoved.push(skipped);
            else moved += 1;
          }
        } catch (err) {
          notMoved.push({
            name: fileIds.length === 1 ? 'The file' : `${fileIds.length} files`,
            reason: err instanceof Error ? err.message : 'could not be moved',
          });
        }
      }
      if (folders.length > 0) {
        queryClient.invalidateQueries({ queryKey: ['attachment-directories-tree'] });
      }
      queryClient.invalidateQueries({ queryKey: ['drive-contents'] });
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      return { moved, notMoved };
    },
    [queryClient, resolveOne]
  );

  const trimmed = name.trim();
  const MoveClashDialog = (
    <Dialog open={clash !== null} onOpenChange={(open) => !open && answer({ kind: 'skip' })}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="line-clamp-2 break-words" title={clash?.message}>
            {clash?.message}
          </DialogTitle>
          <DialogDescription>
            Move it under a new name, replace the file in {clash?.folder_name}, or skip it.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="move-clash-name">New name</Label>
          <Input
            id="move-clash-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter' && trimmed) {
                e.preventDefault();
                answer({ kind: 'rename', name: trimmed });
              }
            }}
          />
        </div>
        <DialogFooter className="flex-col-reverse gap-2 sm:flex-row">
          <Button variant="outline" onClick={() => answer({ kind: 'skip' })}>
            Skip
          </Button>
          {canReplace && (
            <Button variant="outline" onClick={() => answer({ kind: 'replace' })}>
              Replace
            </Button>
          )}
          <Button onClick={() => answer({ kind: 'rename', name: trimmed })} disabled={!trimmed}>
            Rename
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  return { moveFiles, MoveClashDialog };
}
