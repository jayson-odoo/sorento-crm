'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Download, Eye, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import FormNavigation from './FormNavigation';
import LookupBoundLabel from '@/components/common/LookupBoundLabel';
import { useForm, useDeleteForm } from '../../hooks/useForms';
import { useContactAccessTypes } from '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes';
import { formatDate } from '@/lib/helpers';
import { useDownloadAttachment } from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';
import { useQuery } from '@tanstack/react-query';
import { getAttachmentMetadata, getAttachmentPreviewUrl } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import { toast } from 'sonner';

interface FormDetailProps {
  formId: string;
}

export default function FormDetail({ formId }: FormDetailProps) {
  const router = useRouter();
  const { data: form, isLoading } = useForm(formId);
  const downloadMutation = useDownloadAttachment();
  const deleteMutation = useDeleteForm();
  const { data: accessTypeOptions = [] } = useContactAccessTypes();
  const accessLevelNameMap = useMemo(() => {
    const m = new Map<string, string>();
    accessTypeOptions.forEach((o) => m.set(o.code, o.name || o.code));
    return m;
  }, [accessTypeOptions]);
  const [isDownloading, setIsDownloading] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  // Fetch attachment metadata if attachment_id exists
  const { data: attachment } = useQuery({
    queryKey: ['attachment', form?.attachment_id],
    queryFn: () => {
      if (!form?.attachment_id) return null;
      return getAttachmentMetadata(form.attachment_id);
    },
    enabled: !!form?.attachment_id,
  });

  const handleDownload = async () => {
    if (!form?.attachment_id) return;
    
    try {
      setIsDownloading(true);
      const blob = await downloadMutation.mutateAsync(form.attachment_id);
      
      // Create download link
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = attachment?.original_filename || `attachment-${form.attachment_id}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      toast.success('Attachment downloaded successfully');
    } catch {
      toast.error('Failed to download attachment');
    } finally {
      setIsDownloading(false);
    }
  };

  const handlePreview = async () => {
    if (!attachment?.id) return;
    try {
      const previewUrl = await getAttachmentPreviewUrl(attachment.id);
      if (previewUrl) {
        window.open(previewUrl, '_blank');
      }
    } catch {
      toast.error('Failed to open attachment preview');
    }
  };

  const handleDelete = () => {
    deleteMutation.mutate(formId, {
      onSuccess: () => {
        setDeleteDialogOpen(false);
        router.push('/forms-management/forms');
      },
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!form) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Form not found</p>
        <Button variant="outline" onClick={() => router.push('/forms-management/forms')} className="mt-4">
          Back to Forms
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{form.name}</h1>
            <Badge variant={form.is_active ? 'success' : 'secondary'} appearance="ghost">
              {form.is_active ? 'Active' : 'Inactive'}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Form Code: {form.code} • Type:{' '}
            <LookupBoundLabel
              table="forms"
              column="form_type"
              value={form.form_type || 'marketing'}
            />
            {' '}• Version: {form.version} • Language: {form.language.toUpperCase()}
          </p>
        </div>
        <div className="flex gap-2">
          <FormNavigation formId={formId} />
          <Button variant="outline" onClick={() => router.push(`/forms-management/forms/${formId}/edit`)}>
            <Edit className="size-4 mr-2" />
            Edit
          </Button>
          <Button
            variant="outline"
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
            onClick={() => setDeleteDialogOpen(true)}
          >
            <Trash2 className="size-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      {/* Form Information */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Form Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground">Form Code</p>
              <p className="font-medium">{form.code}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Form Name</p>
              <p className="font-medium">{form.name}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Form type</p>
              <p className="font-medium">
                <LookupBoundLabel
                  table="forms"
                  column="form_type"
                  value={form.form_type || 'marketing'}
                />
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Access levels</p>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {(form.access_levels ?? []).length === 0 ? (
                  <span className="text-sm text-muted-foreground">-</span>
                ) : (
                  (form.access_levels ?? []).map((level) => (
                    <Badge key={level} variant="secondary">
                      {accessLevelNameMap.get(level) ?? level}
                    </Badge>
                  ))
                )}
              </div>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Purpose</p>
              <p className="font-medium">{form.purpose || '-'}</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Language</p>
                <p className="font-medium">{form.language.toUpperCase()}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Version</p>
                <p className="font-medium">{form.version}</p>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Created At</p>
                <p className="font-medium">{formatDate(new Date(form.created_at))}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Last Updated</p>
                <p className="font-medium">{formatDate(new Date(form.updated_at))}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Attachment</CardTitle>
          </CardHeader>
          <CardContent>
            {form.attachment_id ? (
              <div className="space-y-3">
                {attachment && (
                  <>
                    <div>
                      <p className="text-sm text-muted-foreground">Filename</p>
                      <p className="font-medium text-sm break-all">{attachment.original_filename}</p>
                    </div>
                    {attachment.file_size_bytes && (
                      <div>
                        <p className="text-sm text-muted-foreground">File Size</p>
                        <p className="font-medium text-sm">
                          {(attachment.file_size_bytes / 1024 / 1024).toFixed(2)} MB
                        </p>
                      </div>
                    )}
                    {attachment.mime_type && (
                      <div>
                        <p className="text-sm text-muted-foreground">File Type</p>
                        <p className="font-medium text-sm">{attachment.mime_type}</p>
                      </div>
                    )}
                  </>
                )}
                <div className="flex gap-2 mt-4">
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="flex-1" 
                    onClick={handlePreview}
                  >
                    <Eye className="size-4 mr-2" />
                    Preview
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    className="flex-1" 
                    onClick={handleDownload}
                    disabled={isDownloading}
                  >
                    <Download className="size-4 mr-2" />
                    {isDownloading ? 'Downloading...' : 'Download'}
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No attachment</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete form</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>{form?.name}</strong> ({form?.code})? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
