'use client';

/**
 * Collapsible session row — single | multi | bulk_zip.
 *
 * For bulk_zip with >25 files we surface a counts dashboard +
 * "Needs attention" subtab (failed + unlinked); "All files" tab is
 * Phase 2 (virtual-scroll).
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  FileSpreadsheet,
  FolderArchive,
  Loader2,
  XCircle,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { timeAgo } from './timeUtil';
import { summariseSession } from './translation';
import type { UploadActivitySession } from './types';
import { UploadFileRow } from './UploadFileRow';

interface Props {
  session: UploadActivitySession;
  defaultExpanded?: boolean;
  onCloseDrawer?: () => void;
}

function StatusBadge({ session }: { session: UploadActivitySession }) {
  const isImportJob = session.session_type === 'import_job';
  switch (session.status) {
    case 'linked':
      return (
        <Badge variant="success" size="sm" className="shrink-0">
          <CheckCircle2 className="size-3" />
          {isImportJob ? 'Finished' : 'Linked'}
        </Badge>
      );
    case 'partial':
      return (
        <Badge variant="warning" size="sm" className="shrink-0">
          Needs review
        </Badge>
      );
    case 'failed':
      return (
        <Badge variant="destructive" size="sm" className="shrink-0">
          <XCircle className="size-3" />
          Failed
        </Badge>
      );
    case 'uploading':
      return (
        <Badge variant="secondary" size="sm" className="shrink-0">
          <Loader2 className="size-3 animate-spin" />
          Uploading
        </Badge>
      );
    case 'processing':
      return (
        <Badge variant="secondary" size="sm" className="shrink-0">
          <Loader2 className="size-3 animate-spin" />
          Processing
        </Badge>
      );
    default:
      return null;
  }
}

export function UploadSessionRow({
  session,
  defaultExpanded = false,
  onCloseDrawer,
}: Props) {
  const router = useRouter();
  const [expanded, setExpanded] = useState(
    defaultExpanded || session.needs_action,
  );

  const isBulk = session.session_type === 'bulk_zip';
  const isMulti = session.session_type === 'multi';
  // Bulk ZIP with many files: default to "Needs attention" subtab inside expanded view.
  const [bulkSubtab, setBulkSubtab] = useState<'needs_action' | 'all'>(
    'needs_action',
  );

  // Excel/data import jobs: no file rows to expand — flat row, whole row
  // navigates to the import-job detail page. (After all hooks — keep order stable.)
  if (session.session_type === 'import_job') {
    return (
      <div className="border-b border-border">
        <button
          type="button"
          onClick={() => {
            if (!session.import_job_id) return;
            onCloseDrawer?.();
            router.push(`/system-management/import-jobs/${session.import_job_id}`);
          }}
          className="w-full flex items-start gap-2 px-4 py-3 hover:bg-muted/40 text-start"
        >
          <FileSpreadsheet className="size-4 mt-0.5 shrink-0 text-muted-foreground" />
          <div className="flex-1 min-w-0">
            {/* See the sibling branch below: the title needs flex-1 + min-w-0 or a
                long filename renders wider than the drawer instead of wrapping. */}
            <div className="flex items-start gap-2 min-w-0">
              <span
                className="font-medium text-sm flex-1 min-w-0 break-words"
                title={session.title}
              >
                {session.title}
              </span>
              <StatusBadge session={session} />
              <span className="ms-auto text-xs text-muted-foreground shrink-0">
                {timeAgo(session.started_at)}
              </span>
            </div>
            <div className="text-xs text-muted-foreground mt-1 truncate">
              {summariseSession(session)}
            </div>
          </div>
          <ExternalLink className="size-3.5 mt-1 shrink-0 text-muted-foreground" />
        </button>
      </div>
    );
  }

  const needsActionFiles = session.files.filter(
    (f) =>
      f.status === 'failed' ||
      f.status === 'post_failed' ||
      f.status === 'unlinked',
  );

  return (
    <div className="border-b border-border">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-start gap-2 px-4 py-3 hover:bg-muted/40 text-start"
      >
        {expanded ? (
          <ChevronDown className="size-4 mt-0.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-4 mt-0.5 shrink-0 text-muted-foreground" />
        )}
        {isBulk && (
          <FolderArchive className="size-4 mt-0.5 shrink-0 text-muted-foreground" />
        )}
        <div className="flex-1 min-w-0">
          {/* min-w-0 + flex-1 on the title: a flex item defaults to min-width:auto,
              so without it the name renders wider than the drawer and spills outside
              it instead of wrapping (truncate alone cannot constrain it). Long import
              filenames wrap to as many lines as they need rather than being cut off. */}
          <div className="flex items-start gap-2 min-w-0">
            <span
              className="font-medium text-sm flex-1 min-w-0 break-words"
              title={session.title}
            >
              {session.title}
            </span>
            <StatusBadge session={session} />
            <span className="ms-auto text-xs text-muted-foreground shrink-0">
              {timeAgo(session.started_at)}
            </span>
          </div>
          <div className="text-xs text-muted-foreground mt-1 truncate">
            {summariseSession(session)}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="bg-muted/20 pb-1">
          {isBulk && session.aggregate.total > 10 ? (
            <>
              <div className="flex items-center gap-1 px-4 pt-2 pb-1 border-b border-border/50">
                <button
                  type="button"
                  className={cn(
                    'text-xs px-2.5 py-1 rounded-md',
                    bulkSubtab === 'needs_action'
                      ? 'bg-background border border-border'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                  onClick={() => setBulkSubtab('needs_action')}
                >
                  Needs attention ({needsActionFiles.length})
                </button>
                <button
                  type="button"
                  className={cn(
                    'text-xs px-2.5 py-1 rounded-md',
                    bulkSubtab === 'all'
                      ? 'bg-background border border-border'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                  onClick={() => setBulkSubtab('all')}
                >
                  All files ({session.aggregate.total})
                </button>
                {session.import_job_id && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ms-auto h-7 px-2 text-xs"
                    onClick={() => {
                      onCloseDrawer?.();
                      router.push(
                        `/resource-management/attachment-directories?import_job_id=${session.import_job_id}`,
                      );
                    }}
                  >
                    <ExternalLink className="size-3 me-1" />
                    Open in Files
                  </Button>
                )}
              </div>
              <div className="max-h-80 overflow-auto">
                {(bulkSubtab === 'needs_action'
                  ? needsActionFiles
                  : session.files
                ).slice(0, 200).map((f) => (
                  <UploadFileRow
                    key={f.client_id}
                    sessionId={session.session_id}
                    file={f}
                    onCloseDrawer={onCloseDrawer}
                  />
                ))}
                {bulkSubtab === 'needs_action' && needsActionFiles.length === 0 && (
                  <div className="px-4 py-6 text-center text-xs text-muted-foreground">
                    All files linked successfully
                  </div>
                )}
                {bulkSubtab === 'all' && session.files.length > 200 && (
                  <div className="px-4 py-2 text-center text-xs text-muted-foreground">
                    Showing first 200 of {session.files.length} —{' '}
                    <button
                      type="button"
                      onClick={() => {
                        onCloseDrawer?.();
                        router.push(
                          `/integration-management/integration-logs?import_job_id=${session.import_job_id}`,
                        );
                      }}
                      className="underline"
                    >
                      view full report
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              {session.files.map((f) => (
                <UploadFileRow
                  key={f.client_id}
                  sessionId={session.session_id}
                  file={f}
                  onCloseDrawer={onCloseDrawer}
                />
              ))}
              {isMulti && session.import_job_id == null && (
                <div className="px-4 py-1 text-[11px] text-muted-foreground">
                  Batch ID:{' '}
                  <span className="font-mono">{session.session_id.slice(0, 8)}</span>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
