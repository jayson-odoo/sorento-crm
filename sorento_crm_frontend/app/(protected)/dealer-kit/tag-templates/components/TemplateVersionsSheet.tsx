'use client';

/**
 * Versions sheet: history newest-first, View opens the read-only canvas
 * (D16), Restore copies a version's doc into the draft (D15) - it never
 * moves the live pointer, so it and Publish stay two different acts even
 * though both start from the same list.
 *
 * Restore runs immediately, no confirmation dialog: PRINCIPLES treats a new
 * destructive-confirm `AlertDialog` as an auto-reject (captain ruling 2 Sep
 * 2026, see the plan's D15/D16 notes and the acceptance criteria file). The
 * host (`[id]/page.tsx`) holds the draft it is about to overwrite in memory
 * before calling this and offers Undo on the success toast instead - this
 * component only needs to disable the ROW being restored while it is in
 * flight.
 */

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Eye, RotateCcw } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { TagTemplateVersion } from '@/lib/dealer-kit/tag-template-types';
import { listTemplateVersions } from '../../services/tagTemplateService';

export function TemplateVersionsSheet({
  templateId,
  open,
  onOpenChange,
  liveVersionNo,
  onView,
  onRestore,
}: {
  templateId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  liveVersionNo: number | null | undefined;
  onView: (versionId: string, versionNo: number) => void;
  onRestore: (versionId: string) => Promise<void>;
}) {
  const [versions, setVersions] = useState<TagTemplateVersion[] | null>(null);
  // The version whose Restore button is currently in flight - disables just
  // that row instead of the whole sheet.
  const [restoringId, setRestoringId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setVersions(null);
    listTemplateVersions(templateId)
      .then(setVersions)
      .catch((err) => {
        toast.error(err instanceof Error ? err.message : 'Failed to load versions');
        setVersions([]);
      });
  }, [open, templateId]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Version history</SheetTitle>
        </SheetHeader>
        <SheetBody className="space-y-1 overflow-y-auto">
          {versions === null && (
            <div className="space-y-2 p-4">
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          )}

          {versions?.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">
              No versions yet. Publish the draft to create version 1.
            </p>
          )}

          {versions?.map((version) => {
            const isLive = version.version_no === liveVersionNo;
            return (
              <div
                key={version.id}
                className="flex flex-col gap-2 border-b px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">Version {version.version_no}</span>
                    {isLive && (
                      <Badge variant="success" className="font-normal">
                        Live
                      </Badge>
                    )}
                  </div>
                  <p className="mt-0.5 truncate text-sm text-muted-foreground">
                    {version.note || 'No note'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {version.created_by_name || 'Unknown'} ·{' '}
                    {formatDateTimeInMalaysia(version.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onView(version.id, version.version_no)}
                  >
                    <Eye className="size-3.5" />
                    View
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={restoringId === version.id}
                    onClick={async () => {
                      setRestoringId(version.id);
                      try {
                        await onRestore(version.id);
                        onOpenChange(false);
                      } finally {
                        setRestoringId(null);
                      }
                    }}
                  >
                    <RotateCcw className="size-3.5" />
                    {restoringId === version.id ? 'Restoring...' : 'Restore'}
                  </Button>
                </div>
              </div>
            );
          })}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}
