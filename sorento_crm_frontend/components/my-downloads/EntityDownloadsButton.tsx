'use client';

/**
 * EntityDownloadsButton - a clickable "print count" chip for one source entity
 * (e.g. a complaint). Clicking opens a modal listing the current user's
 * downloads for that entity; each row is click-to-download (shared DownloadRow).
 *
 * Entity-agnostic: it only ever knows a source type and an id, so it serves the
 * Complaints DataGrid "Print Count" column (count comes from the row), the
 * complaint detail header (count derived from the fetched feed), and the
 * quotation document header (the revision's exports) without a variant each.
 *
 * When `count` is provided we only fetch on open (cheap for a long list). When
 * it's omitted we fetch on mount to derive the count for the chip.
 */

import { useEffect, useState } from 'react';
import { Printer } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { cn } from '@/lib/utils';

import {
  ENTITY_DOWNLOADS_QUERY_KEY,
  fetchDownloadsForEntity,
  type MyDownload,
  type MyDownloadsResponse,
} from '@/services/myDownloadsService';
import { DownloadRow } from './DownloadRow';

function hasInFlight(rows: MyDownload[]): boolean {
  return rows.some((d) => d.status === 'pending' || d.status === 'processing');
}

interface EntityDownloadsButtonProps {
  entityType: string;
  entityId: string;
  /** Display name shown in the modal title (e.g. complaint number). */
  label?: string;
  /** Precomputed count (DataGrid row). Omit to derive it from the feed. */
  count?: number | null;
  className?: string;
  /**
   * Drive the modal from somewhere else - a record page's gear item, where the
   * chip itself has no business sitting (the record card carries the pager, the
   * gear and one primary, nothing else). Supplying this renders the dialog only.
   */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function EntityDownloadsButton({
  entityType,
  entityId,
  label,
  count,
  className,
  open: openProp,
  onOpenChange,
}: EntityDownloadsButtonProps) {
  const [ownOpen, setOwnOpen] = useState(false);
  const controlled = openProp !== undefined;
  const open = controlled ? openProp : ownOpen;
  const setOpen = controlled ? (onOpenChange ?? (() => {})) : setOwnOpen;
  const hasCountProp = typeof count === 'number';

  const query = useQuery<MyDownloadsResponse>({
    queryKey: [...ENTITY_DOWNLOADS_QUERY_KEY, entityType, entityId],
    queryFn: () => fetchDownloadsForEntity(entityType, entityId, 100),
    // Fetch on mount only when we have no count to show; otherwise wait for open.
    enabled: !hasCountProp || open,
    refetchInterval: (q) => {
      const rows = (q.state.data as MyDownloadsResponse | undefined)?.downloads;
      return rows && hasInFlight(rows) ? 4_000 : false;
    },
    refetchIntervalInBackground: false,
    staleTime: 0,
  });

  const rows = query.data?.downloads ?? [];
  const displayCount = hasCountProp ? (count as number) : rows.length;

  // Honour the "no stale data" invariant: force a refetch each time it opens.
  useEffect(() => {
    if (open) void query.refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <>
      {!controlled && (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
        title={label ? `View downloads for ${label}` : 'View downloads for this record'}
        className={cn(
          'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-sm transition-colors hover:bg-muted',
          displayCount > 0 ? 'text-foreground' : 'text-muted-foreground',
          className,
        )}
      >
        <Printer className="size-3.5" />
        <span className="tabular-nums">{displayCount}</span>
      </button>
      )}

      <Dialog open={open} onOpenChange={setOpen} modal>
        <DialogContent
          className="max-w-md p-0 gap-0"
          onClick={(e) => e.stopPropagation()}
        >
          <DialogHeader className="border-b border-border px-4 py-3">
            <DialogTitle className="text-base">
              Downloads{label ? ` · ${label}` : ''}
            </DialogTitle>
          </DialogHeader>
          <DialogBody className="p-0">
            <ScrollArea className="max-h-[60vh] min-h-[120px]">
              {query.isLoading ? (
                <SectionSkeleton rows={3} className="p-4" />
              ) : rows.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-2 px-4 py-12 text-center">
                  <Printer className="size-7 text-muted-foreground/50" />
                  <p className="text-sm font-medium">No downloads yet</p>
                  <p className="text-xs text-muted-foreground">Generate a file and it will appear here.</p>
                </div>
              ) : (
                <div>
                  {rows.map((row) => (
                    <DownloadRow key={row.id} row={row} />
                  ))}
                </div>
              )}
            </ScrollArea>
          </DialogBody>
        </DialogContent>
      </Dialog>
    </>
  );
}
