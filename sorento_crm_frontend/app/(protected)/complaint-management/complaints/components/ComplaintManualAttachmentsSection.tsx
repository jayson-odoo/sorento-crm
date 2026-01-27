'use client';

import { useEffect, useMemo, useState } from 'react';
import { Download, ExternalLink, Link2, Paperclip, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
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
import { Label } from '@/components/ui/label';
import { formatDate } from '@/lib/helpers';
import { useAttachments } from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';
import {
  useComplaintManualAttachments,
  useCreateComplaintManualAttachment,
  useDeleteComplaintManualAttachment,
} from '../hooks/useComplaints';
import { toast } from 'sonner';

interface ComplaintManualAttachmentsSectionProps {
  complaintId: string;
}

export default function ComplaintManualAttachmentsSection({
  complaintId,
}: ComplaintManualAttachmentsSectionProps) {
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const { data: manualAttachments = [], isLoading } =
    useComplaintManualAttachments(complaintId);
  const createMutation = useCreateComplaintManualAttachment();
  const deleteMutation = useDeleteComplaintManualAttachment();

  const { data: attachmentsData, isLoading: isLoadingAttachments } = useAttachments({
    pageIndex: 0,
    pageSize: 100,
    sorting: [],
    searchQuery: '',
  });
  const allAttachments = attachmentsData?.data || [];

  const attachments = useMemo(
    () =>
      manualAttachments
        .map((link) => ({
          ...link,
          attachment: link.attachment || null,
        }))
        .filter((link) => link.attachment),
    [manualAttachments],
  );

  const linkedAttachmentIds = useMemo(
    () => new Set(attachments.map((link) => link.attachment_id)),
    [attachments],
  );
  const availableAttachments = useMemo(
    () => allAttachments.filter((attachment) => !linkedAttachmentIds.has(attachment.id)),
    [allAttachments, linkedAttachmentIds],
  );

  const formatFileSize = (bytes: number | null | undefined) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Paperclip className="size-5" />
          Linked Attachments
        </CardTitle>
        <Button onClick={() => setLinkDialogOpen(true)}>
          <Link2 className="size-4" />
          Link Attachment
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading attachments...</div>
        ) : attachments.length === 0 ? (
          <div className="text-sm text-muted-foreground">No linked attachments.</div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>File Name</TableHead>
                  <TableHead>File Size</TableHead>
                  <TableHead>Linked At</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {attachments.map((link) => {
                  const attachment = link.attachment!;
                  const previewUrl =
                    attachment.file_path?.startsWith('http')
                      ? attachment.file_path
                      : `/api/v1/resource-management/attachments/${attachment.id}/download`;
                  return (
                    <TableRow key={link.id}>
                      <TableCell className="font-medium">
                        {attachment.original_filename || 'Unnamed file'}
                      </TableCell>
                      <TableCell>{formatFileSize(attachment.file_size_bytes)}</TableCell>
                      <TableCell>
                        {formatDate(new Date(link.created_at))}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-2">
                          <Button variant="outline" size="sm" asChild>
                            <a
                              href={previewUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <ExternalLink className="size-4" />
                              View
                            </a>
                          </Button>
                          <Button variant="outline" size="sm" asChild>
                            <a
                              href={`/api/v1/resource-management/attachments/${attachment.id}/download`}
                              download={attachment.original_filename || 'download'}
                            >
                              <Download className="size-4" />
                              Download
                            </a>
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => deleteMutation.mutate(link.id)}
                            disabled={deleteMutation.isPending}
                          >
                            <Trash2 className="size-4" />
                            Unlink
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
      {linkDialogOpen && (
        <LinkAttachmentDialog
          open={linkDialogOpen}
          onOpenChange={setLinkDialogOpen}
          complaintId={complaintId}
          availableAttachments={availableAttachments}
          isLoading={isLoadingAttachments}
        />
      )}
    </Card>
  );
}

interface LinkAttachmentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  complaintId: string;
  availableAttachments: Array<{ id: string; original_filename: string }>;
  isLoading: boolean;
}

function LinkAttachmentDialog({
  open,
  onOpenChange,
  complaintId,
  availableAttachments,
  isLoading,
}: LinkAttachmentDialogProps) {
  const [selectedAttachmentId, setSelectedAttachmentId] = useState<string>('');
  const createMutation = useCreateComplaintManualAttachment();

  useEffect(() => {
    if (!open) {
      setSelectedAttachmentId('');
    }
  }, [open]);

  const handleLink = async () => {
    if (!selectedAttachmentId) {
      toast.error('Please select an attachment');
      return;
    }
    await createMutation.mutateAsync({
      complaint_id: complaintId,
      attachment_id: selectedAttachmentId,
    });
    setSelectedAttachmentId('');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Link Existing Attachment</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Attachment</Label>
            {isLoading ? (
              <div className="text-sm text-muted-foreground">Loading attachments...</div>
            ) : (
              <Select value={selectedAttachmentId} onValueChange={setSelectedAttachmentId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select an attachment..." />
                </SelectTrigger>
                <SelectContent>
                  {availableAttachments.map((attachment) => (
                    <SelectItem key={attachment.id} value={attachment.id}>
                      {attachment.original_filename}
                    </SelectItem>
                  ))}
                  {availableAttachments.length === 0 && (
                    <SelectItem value="__no_attachments__" disabled>
                      No available attachments
                    </SelectItem>
                  )}
                </SelectContent>
              </Select>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleLink}
              disabled={!selectedAttachmentId || createMutation.isPending}
            >
              {createMutation.isPending ? 'Linking...' : 'Link Attachment'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
