'use client';

import * as React from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Eye, Trash2, Upload } from 'lucide-react';
import { toast } from '@/lib/toast';
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
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import {
  type ProjectDocument,
  type UploadConflictChoice,
  deleteProjectDocument,
  listProjectDocuments,
  resolveProjectDocumentTypeId,
  uploadProjectDocument,
} from '../../_shared/services/projectDocumentService';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
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
  const [previewIndex, setPreviewIndex] = React.useState<number | null>(null);

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

  const rows = React.useMemo(() => documents.data ?? [], [documents.data]);

  /**
   * The SAME preview the Files screen opens: zoom, pan, page through the whole list.
   * Built over every row rather than one, so opening a drawing and paging to the next
   * costs no round trip.
   */
  const previewItems = React.useMemo<AttachmentPreviewItem[]>(
    () =>
      rows.map((row) => ({
        id: row.id,
        name: row.stored_filename ?? row.original_filename ?? 'Unnamed file',
        url: row.file_path ?? '',
        downloadUrl: `/api/v1/resource-management/attachments/${row.id}/download`,
        sizeBytes: row.file_size_bytes ?? null,
      })),
    [rows],
  );

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
              mode="icon"
              variant="ghost"
              size="sm"
              onClick={() => setPreviewIndex(row.index)}
              aria-label={`Preview ${row.original.original_filename ?? 'this document'}`}
            >
              <Eye className="size-3.5" />
            </Button>
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
        size: 130,
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
        // No second button in the middle of the empty state: the one in the toolbar is
        // where it lives, and a centred duplicate is another thing to read.
        emptyTitle="No documents on this project"
        searchPlaceholder="Search documents"
        searchOf={(row) =>
          [
            row.stored_filename,
            row.original_filename,
            row.attachment_type?.type_name,
            row.uploaded_by_user?.name,
          ]
            .filter(Boolean)
            .join(' ')
        }
        // The row opens the preview, per ADR 1d: the eye is for people who look for a button.
        onRowClick={(row) => {
          const index = rows.findIndex((candidate) => candidate.id === row.id);
          if (index >= 0) setPreviewIndex(index);
        }}
      />

      <AttachmentPreviewModal
        open={previewIndex !== null}
        onOpenChange={(next) => !next && setPreviewIndex(null)}
        items={previewItems}
        startIndex={previewIndex ?? 0}
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
  const [busy, setBusy] = React.useState(false);
  /** Files the server said already exist here, held until the user decides what to do. */
  const [conflicts, setConflicts] = React.useState<File[]>([]);

  /**
   * Uploads sequentially, and returns whatever came back as a conflict.
   *
   * Sequential rather than parallel: the endpoint is per file, and a burst of ten concurrent
   * multipart POSTs of tender drawings times out the slowest with no way to say WHICH failed.
   */
  async function send(batch: File[], onConflict?: UploadConflictChoice) {
    const failed: string[] = [];
    const clashed: File[] = [];
    let uploaded = 0;

    let typeId: string;
    try {
      typeId = await resolveProjectDocumentTypeId();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not resolve the document type');
      return { uploaded: 0, clashed: [], failed: [] };
    }

    for (const file of batch) {
      try {
        const outcome = await uploadProjectDocument(projectId, file, typeId, onConflict);
        if (outcome.status === 'conflict') clashed.push(file);
        else uploaded += 1;
      } catch (error) {
        failed.push(`${file.name}: ${error instanceof Error ? error.message : 'failed'}`);
      }
    }

    if (uploaded > 0) {
      toast.success(`${uploaded} document${uploaded === 1 ? '' : 's'} uploaded`);
      onUploaded();
    }
    // Named, not counted: "2 failed" leaves the user guessing which two to retry.
    failed.forEach((message) => toast.error(message));
    return { uploaded, clashed, failed };
  }

  async function submit() {
    setBusy(true);
    const { clashed, failed } = await send(files);
    setBusy(false);
    if (clashed.length > 0) {
      setConflicts(clashed);
      return;
    }
    if (failed.length === 0) onDone();
    else setFiles([]);
  }

  async function resolveConflicts(choice: UploadConflictChoice) {
    setBusy(true);
    const batch = conflicts;
    setConflicts([]);
    const { failed } = await send(batch, choice);
    setBusy(false);
    if (failed.length === 0) onDone();
  }

  if (conflicts.length > 0) {
    return (
      <Dialog open onOpenChange={(next) => !next && setConflicts([])}>
        <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
          <DialogHeader>
            <DialogTitle>
              {conflicts.length === 1
                ? 'A file with this name is already here'
                : `${conflicts.length} files with these names are already here`}
            </DialogTitle>
          </DialogHeader>
          <DialogBody className="max-h-[50vh] overflow-y-auto">
            <ul className="space-y-1">
              {conflicts.map((file) => (
                <li key={file.name} className="break-all text-sm">
                  {file.name}
                </li>
              ))}
            </ul>
          </DialogBody>
          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone} disabled={busy}>
              Cancel
            </Button>
            {/* Keep both is first and outlined, replace is the destructive one: replacing
                overwrites bytes somebody else may be linking to. */}
            <Button
              type="button"
              variant="outline"
              onClick={() => resolveConflicts('copy')}
              disabled={busy}
            >
              Keep both
            </Button>
            <Button
              type="button"
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => resolveConflicts('replace')}
              disabled={busy}
            >
              Replace
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>Upload documents</DialogTitle>
        </DialogHeader>
        <DialogBody className="max-h-[60vh] overflow-y-auto">
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
          <Button type="button" onClick={submit} disabled={files.length === 0 || busy}>
            {busy ? 'Uploading…' : `Upload ${files.length || ''}`.trim()}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
