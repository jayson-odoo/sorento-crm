'use client';

/**
 * The Attachment action set (D15).
 *
 * The file browser's row menu and the record page's gear render this one array,
 * in this order. Before it, the row carried four or five icon buttons and the
 * record's gear carried a different four, so Rename was list-only and Restore
 * was record-only.
 *
 * Preview is not here: it is the record's primary button, and on the list the
 * row click opens the record. That is the rule for a primary action.
 */

import { useState } from 'react';
import { Download, Pencil, RefreshCw, RotateCcw, Trash2 } from 'lucide-react';
import { toast } from '@/lib/toast';
import { useQueryClient } from '@tanstack/react-query';

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { RecordAction, RecordActionSet } from '@/components/common/recordActions';
import {
  useDownloadAttachment,
  useResubmitAttachmentWebhook,
  useRestoreAttachment,
  useUpdateAttachment,
} from './hooks/useAttachments';
import type { Attachment } from './types/attachment.types';
import AttachmentDeleteDialog from './components/attachment-delete-dialog';

export interface UseAttachmentActionsOptions {
  /** Where to go once the file is gone (the record page returns to the list). */
  onDeleted?: () => void;
}

export function useAttachmentActions(
  attachment: Attachment | null | undefined,
  { onDeleted }: UseAttachmentActionsOptions = {},
): RecordActionSet {
  const queryClient = useQueryClient();
  const downloadMutation = useDownloadAttachment();
  const updateMutation = useUpdateAttachment();
  const resubmitMutation = useResubmitAttachmentWebhook();
  const restoreMutation = useRestoreAttachment();

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState('');

  if (!attachment) return { actions: [] };

  const currentName = attachment.stored_filename || attachment.original_filename || '';

  const download = async () => {
    try {
      const blob = await downloadMutation.mutateAsync(attachment.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = currentName || 'download';
      document.body.appendChild(link);
      link.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(link);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to download');
    }
  };

  const submitRename = async () => {
    const next = renameValue.trim();
    if (!next) {
      toast.error('Filename cannot be empty.');
      return;
    }
    if (next === currentName) {
      setRenameOpen(false);
      return;
    }
    try {
      await updateMutation.mutateAsync({
        attachmentId: attachment.id,
        data: { stored_filename: next },
      });
      toast.success('Renamed.');
      setRenameOpen(false);
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      queryClient.invalidateQueries({ queryKey: ['attachment-metadata', attachment.id] });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Rename failed.');
    }
  };

  const actions: RecordAction[] = [
    {
      key: 'attachment.download',
      label: 'Download',
      icon: Download,
      disabled: downloadMutation.isPending,
      run: () => void download(),
    },
    {
      key: 'attachment.rename',
      label: 'Rename',
      icon: Pencil,
      disabled: attachment.is_deleted,
      run: () => {
        setRenameValue(currentName);
        setRenameOpen(true);
      },
    },
    {
      key: 'attachment.resubmit',
      label: 'Resubmit',
      icon: RefreshCw,
      disabled: resubmitMutation.isPending || attachment.is_deleted,
      run: () => resubmitMutation.mutate(attachment.id),
    },
  ];

  if (attachment.is_deleted) {
    actions.push({
      key: 'attachment.restore',
      label: 'Restore',
      icon: RotateCcw,
      disabled: restoreMutation.isPending,
      run: () => restoreMutation.mutate(attachment.id),
    });
  }

  actions.push({
    key: 'attachment.delete',
    // A trashed file is deleted for good; a live one only goes to the trash, and
    // the label has to say which, because one of the two cannot be undone.
    label: attachment.is_deleted ? 'Permanently delete' : 'Move to trash',
    icon: Trash2,
    kind: 'destructive',
    run: () => setDeleteOpen(true),
  });

  const dialogs = (
    <>
      <AttachmentDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        attachment={attachment}
        permanent={attachment.is_deleted}
        onSuccess={onDeleted}
      />

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Rename file</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="rename-input">
              Filename <span className="text-destructive">*</span>
            </Label>
            <Input
              id="rename-input"
              value={renameValue}
              onChange={(event) => setRenameValue(event.target.value)}
              placeholder="new-filename.ext"
              autoFocus
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !updateMutation.isPending) {
                  event.preventDefault();
                  void submitRename();
                }
              }}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRenameOpen(false)}
              disabled={updateMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={() => void submitRename()}
              disabled={updateMutation.isPending || !renameValue.trim()}
            >
              {updateMutation.isPending ? 'Saving…' : 'Rename'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );

  return { actions, dialogs };
}
