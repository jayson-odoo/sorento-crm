'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Download, Eye, RefreshCw, Trash2, ExternalLink } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { useQueryClient } from '@tanstack/react-query';
import { LoaderCircleIcon } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { formatDate } from '@/lib/helpers';
import RecordNavigation from '@/components/common/RecordNavigation';
import {
  useAttachments,
  useDeleteAttachment,
  useDownloadAttachment,
  useResubmitAttachmentWebhook,
  useRestoreAttachment,
  useUpdateAttachment,
} from '../hooks/useAttachments';
import { getAttachmentMetadata } from '../services/attachmentService';
import type { Attachment } from '../types/attachment.types';
import AttachmentDeleteDialog from './attachment-delete-dialog';

const ENTITY_ROUTES = {
  product: { label: 'Product', path: '/master-data-management/products' },
  promotion: { label: 'Promotion', path: '/marketing-management/promotions' },
  form: { label: 'Form', path: '/forms-management/forms' },
} as const;

const ACCESS_LEVEL_OPTIONS = [
  { value: 'dealer', label: 'Dealer' },
  { value: 'end_user', label: 'End User' },
] as const;

function LinkedEntityLink({
  type,
  id,
  name,
}: {
  type: keyof typeof ENTITY_ROUTES;
  id: string;
  name: string;
}) {
  const config = ENTITY_ROUTES[type];
  const href = `${config.path}/${id}`;
  return (
    <Link
      href={href}
      className="text-primary hover:underline inline-flex items-center gap-1"
    >
      {name}
      <ExternalLink className="size-3.5 shrink-0" />
    </Link>
  );
}

function LinkagesTable({
  type,
  items,
  emptyMessage,
}: {
  type: keyof typeof ENTITY_ROUTES;
  items: Array<{ id: string; name: string; description?: string | null }>;
  emptyMessage: string;
}) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">{emptyMessage}</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Description</TableHead>
          <TableHead className="w-[80px]">Action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.id}>
            <TableCell className="font-medium">{item.name}</TableCell>
            <TableCell className="text-muted-foreground max-w-md line-clamp-2" title={item.description ?? undefined}>
              {item.description ?? '—'}
            </TableCell>
            <TableCell>
              <Link
                href={`${ENTITY_ROUTES[type].path}/${item.id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline inline-flex items-center gap-1 text-sm"
              >
                View
                <ExternalLink className="size-3.5 shrink-0" />
              </Link>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function LinkagesTabs({ attachment }: { attachment: Attachment }) {
  const products = attachment.linked_products ?? [];
  const promotions = attachment.linked_promotions ?? [];
  const form = attachment.linked_form ?? null;

  return (
    <Tabs defaultValue="products" className="w-full">
      <TabsList className="grid w-full grid-cols-3">
        <TabsTrigger value="products">
          Products {products.length > 0 && `(${products.length})`}
        </TabsTrigger>
        <TabsTrigger value="promotions">
          Promotions {promotions.length > 0 && `(${promotions.length})`}
        </TabsTrigger>
        <TabsTrigger value="forms">
          Forms {form ? '(1)' : ''}
        </TabsTrigger>
      </TabsList>
      <TabsContent value="products" className="mt-4">
        <LinkagesTable
          type="product"
          items={products}
          emptyMessage="No products linked to this attachment."
        />
      </TabsContent>
      <TabsContent value="promotions" className="mt-4">
        <LinkagesTable
          type="promotion"
          items={promotions}
          emptyMessage="No promotions linked to this attachment."
        />
      </TabsContent>
      <TabsContent value="forms" className="mt-4">
        {form ? (
          <LinkagesTable
            type="form"
            items={[form]}
            emptyMessage="No form linked to this attachment."
          />
        ) : (
          <p className="text-sm text-muted-foreground">No form linked to this attachment.</p>
        )}
      </TabsContent>
    </Tabs>
  );
}

interface AttachmentDetailProps {
  attachmentId: string;
  fromDirectories?: boolean;
  directoryId?: string;
}

export default function AttachmentDetail({
  attachmentId,
  fromDirectories = false,
  directoryId,
}: AttachmentDetailProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [descriptionEdit, setDescriptionEdit] = useState<string | null>(null);
  const [accessLevelsEdit, setAccessLevelsEdit] = useState<string[] | null>(null);
  const deleteMutation = useDeleteAttachment();
  const downloadMutation = useDownloadAttachment();
  const resubmitMutation = useResubmitAttachmentWebhook();
  const restoreMutation = useRestoreAttachment();
  const updateMutation = useUpdateAttachment();

  const { data: attachment, isLoading } = useQuery({
    queryKey: ['attachment-metadata', attachmentId],
    queryFn: () => getAttachmentMetadata(attachmentId),
    enabled: !!attachmentId,
    retry: 1,
  });

  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'uploaded_at', desc: true }],
      searchQuery: '',
    }),
    [],
  );
  const { data: navigationData } = useAttachments(navigationParams);
  const navigationItems = navigationData?.data ?? [];

  const formatFileSize = (bytes: number | null | undefined) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const handleDownload = async (file: Attachment) => {
    try {
      const blob = await downloadMutation.mutateAsync(file.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.original_filename || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      // handled by toast in mutation
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  const listPath = fromDirectories
    ? `/resource-management/attachment-directories${directoryId ? `?directoryId=${directoryId}` : ''}`
    : '/resource-management/attachments';

  if (!attachment) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Attachment not found</p>
        <Button
          variant="outline"
          onClick={() => router.push(listPath)}
          className="mt-4"
        >
          Back to {fromDirectories ? 'Attachment Directories' : 'Attachments'}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold">{attachment.original_filename}</h1>
          <p className="text-sm text-muted-foreground">
            Uploaded: {formatDate(new Date(attachment.uploaded_at))}
          </p>
        </div>
        <div className="flex gap-2">
          <RecordNavigation
            currentId={attachmentId}
            items={navigationItems}
            basePath={listPath}
          />
          <Button
            variant="outline"
            onClick={() => {
              const fp = attachment.file_path || '';
              const url =
                fp.startsWith('http://') || fp.startsWith('https://')
                  ? fp
                  : `${typeof window !== 'undefined' ? window.location.origin : ''}/api/v1/resource-management/attachments/${attachment.id}/download`;
              window.open(url, '_blank', 'noopener,noreferrer');
            }}
          >
            <Eye className="size-4" />
            Preview
          </Button>
          <Button
            variant="outline"
            onClick={() => handleDownload(attachment)}
            disabled={downloadMutation.isPending}
          >
            <Download className="size-4" />
            Download
          </Button>
          <Button
            variant="outline"
            onClick={() => resubmitMutation.mutate(attachment.id)}
            disabled={resubmitMutation.isPending || attachment.is_deleted}
          >
            <RefreshCw className={`size-4 ${resubmitMutation.isPending ? 'animate-spin' : ''}`} />
            Resubmit
          </Button>
          {attachment.is_deleted ? (
            <>
              <Button
                variant="outline"
                onClick={() => restoreMutation.mutate(attachment.id)}
                disabled={restoreMutation.isPending}
              >
                Restore
              </Button>
              <Button variant="destructive" onClick={() => setDeleteDialogOpen(true)}>
                <Trash2 className="size-4" />
                Permanently Delete
              </Button>
            </>
          ) : (
            <Button variant="destructive" onClick={() => setDeleteDialogOpen(true)}>
              <Trash2 className="size-4" />
              Move to Trash
            </Button>
          )}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Attachment Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">File Type</p>
              <p className="font-medium">{attachment.mime_type || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">File Size</p>
              <p className="font-medium">{formatFileSize(attachment.file_size_bytes)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Uploaded By</p>
              <p className="font-medium">
                {attachment.uploaded_by_user?.name ?? attachment.uploaded_by_user?.email ?? attachment.uploaded_by ?? '-'}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <Badge
                variant={attachment.is_deleted ? 'destructive' : 'success'}
                appearance="ghost"
              >
                <BadgeDot />
                {attachment.is_deleted ? 'Deleted' : 'Active'}
              </Badge>
            </div>
          </div>
          <div className="space-y-2">
            <Label className="text-sm text-muted-foreground">Description</Label>
            {descriptionEdit !== null ? (
              <div className="space-y-2">
                <textarea
                  className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  value={descriptionEdit}
                  onChange={(e) => setDescriptionEdit(e.target.value)}
                  placeholder="Add a description..."
                />
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => {
                      updateMutation.mutate(
                        { attachmentId: attachment.id, data: { description: descriptionEdit || null } },
                        {
                          onSuccess: () => {
                            queryClient.invalidateQueries({ queryKey: ['attachment-metadata', attachment.id] });
                            setDescriptionEdit(null);
                          },
                        }
                      );
                    }}
                    disabled={updateMutation.isPending}
                  >
                    {updateMutation.isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : 'Save'}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setDescriptionEdit(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-start justify-between gap-2">
                <p className="font-medium text-sm min-h-[1.5rem]">
                  {attachment.description?.trim() || '—'}
                </p>
                <Button variant="ghost" size="sm" onClick={() => setDescriptionEdit(attachment.description ?? '')}>
                  {attachment.description?.trim() ? 'Edit' : 'Add'}
                </Button>
              </div>
            )}
          </div>
          <div className="space-y-2">
            <Label className="text-sm text-muted-foreground">Access levels</Label>
            {accessLevelsEdit !== null ? (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-4">
                  {ACCESS_LEVEL_OPTIONS.map((opt) => (
                    <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
                      <Checkbox
                        checked={accessLevelsEdit.includes(opt.value)}
                        onCheckedChange={(checked) => {
                          setAccessLevelsEdit((prev) => {
                            const arr = prev ?? [];
                            if (checked) return arr.includes(opt.value) ? arr : [...arr, opt.value];
                            return arr.filter((v) => v !== opt.value);
                          });
                        }}
                      />
                      <span className="text-sm">{opt.label}</span>
                    </label>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() => {
                      const levels = accessLevelsEdit?.length ? accessLevelsEdit : ['dealer', 'end_user'];
                      updateMutation.mutate(
                        { attachmentId: attachment.id, data: { access_levels: levels } },
                        {
                          onSuccess: () => {
                            queryClient.invalidateQueries({ queryKey: ['attachment-metadata', attachment.id] });
                            setAccessLevelsEdit(null);
                          },
                        }
                      );
                    }}
                    disabled={updateMutation.isPending}
                  >
                    {updateMutation.isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : 'Save'}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setAccessLevelsEdit(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex items-start justify-between gap-2">
                <div className="flex flex-wrap gap-2">
                  {(attachment.access_levels ?? []).length === 0 ? (
                    <span className="text-sm text-muted-foreground">—</span>
                  ) : (
                    (attachment.access_levels ?? []).map((level) => (
                      <Badge key={level} variant="secondary">
                        {level === 'dealer' ? 'Dealer' : 'End User'}
                      </Badge>
                    ))
                  )}
                </div>
                <Button variant="ghost" size="sm" onClick={() => setAccessLevelsEdit(attachment.access_levels ?? ['dealer', 'end_user'])}>
                  Edit
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Linkages</CardTitle>
        </CardHeader>
        <CardContent>
          <LinkagesTabs attachment={attachment} />
        </CardContent>
      </Card>

      <AttachmentDeleteDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        attachment={attachment}
        permanent={attachment.is_deleted}
      />
    </div>
  );
}
