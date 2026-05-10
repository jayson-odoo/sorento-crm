'use client';

/**
 * EditAttachmentTypeDialog — change attachment_type_id on one or many
 * attachments. Used by:
 *   - the per-attachment Edit button in AttachmentDetailModal.
 *   - the Files toolbar bulk action when 1+ rows are selected.
 *
 * Backend: POST /api/v1/resource-management/attachments/bulk-attachment-type
 * — does NOT trigger any webhook resubmission.
 */
import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { useAttachmentTypesList } from '../hooks/useAttachments';
import type { AttachmentType } from '../../attachment-types/types/attachmentType.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  attachmentIds: string[];
  /** Pre-fill the picker with the attachment's current type when single-edit. */
  initialAttachmentTypeId?: string | null;
  onSaved?: () => void;
}

export default function EditAttachmentTypeDialog({
  open,
  onOpenChange,
  attachmentIds,
  initialAttachmentTypeId,
  onSaved,
}: Props) {
  const queryClient = useQueryClient();
  const { data: attachmentTypes = [], isLoading } = useAttachmentTypesList();
  const [selectedTypeId, setSelectedTypeId] = useState<string>('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setSelectedTypeId(initialAttachmentTypeId ?? '');
    }
  }, [open, initialAttachmentTypeId]);

  const isBulk = attachmentIds.length > 1;

  const handleSave = async () => {
    if (!selectedTypeId) {
      toast.error('Pick an attachment type first.');
      return;
    }
    if (attachmentIds.length === 0) {
      toast.error('No attachments selected.');
      return;
    }
    setSaving(true);
    try {
      const r = await apiFetch(
        '/api/v1/resource-management/attachments/bulk-attachment-type',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            attachment_ids: attachmentIds,
            attachment_type_id: selectedTypeId,
          }),
        },
      );
      if (!r.ok) {
        throw new Error(
          await extractApiError(r, 'Failed to update attachment type'),
        );
      }
      const body = await r.json();
      toast.success(
        `Updated ${body.updated_attachments} attachment${
          body.updated_attachments === 1 ? '' : 's'
        }.`,
      );
      queryClient.invalidateQueries({ queryKey: ['attachments'] });
      queryClient.invalidateQueries({ queryKey: ['attachment-metadata'] });
      onSaved?.();
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to update attachment type');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isBulk ? `Change attachment type (${attachmentIds.length})` : 'Change attachment type'}
          </DialogTitle>
          <DialogDescription>
            {isBulk
              ? 'Reassigns the attachment type for all selected files. Does not trigger any webhook resubmission.'
              : 'Reassigns the attachment type for this file. Does not trigger any webhook resubmission.'}
          </DialogDescription>
        </DialogHeader>

        <div className="py-2 space-y-2">
          <Select
            value={selectedTypeId}
            onValueChange={setSelectedTypeId}
            disabled={isLoading || saving}
          >
            <SelectTrigger data-testid="edit-attachment-type-trigger">
              <SelectValue placeholder="Select attachment type" />
            </SelectTrigger>
            <SelectContent>
              {attachmentTypes.map((type: AttachmentType) => (
                <SelectItem key={type.id} value={type.id}>
                  {type.type_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving || !selectedTypeId}
            data-testid="edit-attachment-type-save"
          >
            {saving ? (
              <>
                <Loader2 className="size-4 animate-spin mr-2" />
                Saving…
              </>
            ) : (
              'Save'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
