'use client';

import * as React from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Trash2, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { FileDropzone } from '@/components/common/FileDropzone';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  type ProjectDocument,
  deleteProjectDocument,
  listAttachmentTypeOptions,
  listProjectDocuments,
  uploadProjectDocument,
} from '../../_shared/services/projectDocumentService';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import type { Project } from '../../_shared/types/project.types';

/**
 * Tender documents and drawings on this project.
 *
 * The tab used to be a paragraph SAYING documents attach through the shared attachment
 * directory, with no way to attach one. It now does it: the same `attachments` endpoint
 * Resource Management → Files uses, with `entity_type=project`, so a drawing uploaded here
 * is one row - visible on the Files screen, in the trash, and to the storage migration.
 */
function formatSize(bytes?: number | null): string {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ProjectDocumentsPanel({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const [uploading, setUploading] = React.useState(false);
  const [deleting, setDeleting] = React.useState<ProjectDocument | null>(null);

  const documents = useQuery({
    queryKey: ['project-documents', project.id],
    queryFn: () => listProjectDocuments(project.id),
  });

  const remove = useMutation({
    mutationFn: (attachmentId: string) => deleteProjectDocument(attachmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-documents', project.id] });
    },
  });

  const rows = documents.data ?? [];

  const columns = React.useMemo<ColumnDef<ProjectDocument>[]>(
    () => [
      {
        id: 'name',
        accessorFn: (row) => row.stored_filename ?? row.original_filename ?? '',
        header: ({ column }) => <DataGridColumnHeader title="File" column={column} />,
        cell: ({ row }) => {
          const name =
            row.original.stored_filename ?? row.original.original_filename ?? 'Unnamed file';
          return (
            <span className="truncate text-sm font-medium" title={name}>
              {name}
            </span>
          );
        },
        size: 320,
        meta: { headerTitle: 'File' },
      },
      {
        id: 'attachment_type_name',
        accessorFn: (row) => row.attachment_type?.type_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        cell: ({ row }) =>
          row.original.attachment_type?.type_name ? (
            <span className="truncate text-sm">{row.original.attachment_type.type_name}</span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 160,
        meta: { headerTitle: 'Type' },
      },
      {
        id: 'file_size',
        accessorFn: (row) => row.file_size_bytes ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Size" column={column} />,
        cell: ({ row }) => (
          <span className="truncate text-sm">{formatSize(row.original.file_size_bytes)}</span>
        ),
        size: 110,
        meta: { headerTitle: 'Size' },
      },
      {
        id: 'uploaded_by_name',
        accessorFn: (row) => row.uploaded_by_user?.name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Uploaded by" column={column} />,
        cell: ({ row }) =>
          row.original.uploaded_by_user?.name ? (
            <span className="truncate text-sm">{row.original.uploaded_by_user.name}</span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 170,
        meta: { headerTitle: 'Uploaded by' },
      },
      {
        id: 'uploaded_at',
        accessorFn: (row) => row.uploaded_at ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Uploaded" column={column} />,
        cell: ({ row }) =>
          row.original.uploaded_at ? (
            <span className="truncate text-sm">
              {formatDateTimeInMalaysia(row.original.uploaded_at)}
            </span>
          ) : (
            <span className="text-muted-foreground">-</span>
          ),
        size: 190,
        meta: { headerTitle: 'Uploaded' },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1" onClick={(event) => event.stopPropagation()}>
            <Button
              asChild
              mode="icon"
              variant="ghost"
              size="sm"
              aria-label={`Download ${row.original.original_filename ?? 'this document'}`}
            >
              <a
                href={`/api/v1/resource-management/attachments/${row.original.id}/download`}
                download
              >
                <Download className="size-3.5" />
              </a>
            </Button>
            {project.can_edit && (
              <Button
                mode="icon"
                variant="ghost"
                size="sm"
                onClick={() => setDeleting(row.original)}
                aria-label={`Delete ${row.original.original_filename ?? 'this document'}`}
              >
                <Trash2 className="size-3.5 text-destructive" />
              </Button>
            )}
          </div>
        ),
        size: 100,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [project.can_edit],
  );

  return (
    <>
      <PanelDataGrid
        title="Documents"
        toolbar={
          project.can_edit ? (
            <Button type="button" size="sm" onClick={() => setUploading(true)}>
              <Upload className="size-4" aria-hidden />
              Upload documents
            </Button>
          ) : undefined
        }
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        listingKey="projects.projects.view::project-documents"
        isLoading={documents.isLoading}
        error={documents.isError ? documents.error : undefined}
        emptyTitle="No documents on this project"
        emptyAction={
          project.can_edit ? (
            <Button type="button" onClick={() => setUploading(true)}>
              <Upload className="size-4" aria-hidden />
              Upload the first document
            </Button>
          ) : undefined
        }
      />

      {uploading && (
        <UploadDialog
          projectId={project.id}
          onDone={() => setUploading(false)}
          onUploaded={() =>
            queryClient.invalidateQueries({ queryKey: ['project-documents', project.id] })
          }
        />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        onOpenChange={(next) => !next && setDeleting(null)}
        title="Confirm delete"
        description={
          deleting
            ? `Delete ${deleting.original_filename ?? 'this document'}? This action cannot be undone.`
            : ''
        }
        onDelete={async () => {
          if (!deleting) return;
          await remove.mutateAsync(deleting.id);
        }}
        onSuccess={() => setDeleting(null)}
        successMessage="Document deleted"
      />
    </>
  );
}

/**
 * One drop, many files.
 *
 * Uploads are sequential rather than parallel: the endpoint is per-file, and a burst of ten
 * concurrent multipart POSTs of tender drawings is how you get a timeout on the slowest one
 * with no way to tell the user WHICH failed. Each result is reported by name.
 */
function UploadDialog({
  projectId,
  onDone,
  onUploaded,
}: {
  projectId: string;
  onDone: () => void;
  onUploaded: () => void;
}) {
  const [files, setFiles] = React.useState<File[]>([]);
  const [typeId, setTypeId] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  // Required by the endpoint, not a nicety: the type decides the storage prefix and whether
  // the n8n webhook fires, and an upload without one is refused with a 400.
  const types = useQuery({
    queryKey: ['attachment-type-options'],
    queryFn: listAttachmentTypeOptions,
  });

  async function submit() {
    setBusy(true);
    const failed: string[] = [];
    let uploaded = 0;
    for (const file of files) {
      try {
        await uploadProjectDocument(projectId, file, typeId);
        uploaded += 1;
      } catch (error) {
        failed.push(`${file.name}: ${error instanceof Error ? error.message : 'failed'}`);
      }
    }
    setBusy(false);
    if (uploaded > 0) {
      toast.success(`${uploaded} document${uploaded === 1 ? '' : 's'} uploaded`);
      onUploaded();
    }
    // Named, not counted: "2 failed" leaves the user guessing which two to retry.
    failed.forEach((message) => toast.error(message));
    if (failed.length === 0) onDone();
    else setFiles([]);
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>Upload documents</DialogTitle>
        </DialogHeader>
        <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
          <div className="space-y-1.5">
            <Label htmlFor="project-document-type">
              Document type <span className="text-destructive">*</span>
            </Label>
            <SearchableSelect
              id="project-document-type"
              value={typeId}
              onChange={setTypeId}
              disabled={busy}
              options={(types.data ?? []).map((type) => ({
                value: type.id,
                label: type.type_name,
                description: type.code ?? undefined,
              }))}
              placeholder="Choose a document type"
              emptyMessage="No document types yet. Add one under Resource Management"
            />
          </div>
          <FileDropzone
            multiple
            files={files}
            onFilesChange={setFiles}
            maxSizeMb={50}
            disabled={busy}
            aria-label="Project documents"
            onReject={(file, reason) =>
              toast.error(
                reason === 'size'
                  ? `${file.name} is over 50 MB`
                  : `${file.name} cannot be uploaded`,
              )
            }
          />
        </DialogBody>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={onDone} disabled={busy}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={submit}
            disabled={files.length === 0 || !typeId || busy}
          >
            {busy ? 'Uploading…' : `Upload ${files.length || ''}`.trim()}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
