'use client';

/**
 * A request's design history (r9 S5/D19).
 *
 * Lifted from `TemplateVersionsSheet`, which does the same job for a template:
 * newest first, View draws the version read-only, Restore copies it back onto
 * the draft. The differences are what a REQUEST version is - a whole sheet
 * document plus the product data that was pinned when it was written - so View
 * opens the shared `DesignLightbox` rather than the template editor's
 * single-tag canvas, and Restore writes a new version rather than moving a
 * live pointer.
 *
 * Restore runs immediately, no confirmation dialog: it ADDS a version
 * ("Restored v<n>") rather than destroying one, so the way back is the list
 * this sheet is showing.
 */

import { useCallback, useEffect, useState } from 'react';
import { Eye, RotateCcw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from '@/lib/toast';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { RequestVersionSummary } from '@/lib/dealer-kit/product-data-changes';

interface RequestVersionsSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The document number, so the sheet says which request it is about. */
  docNumber: string;
  load: () => Promise<RequestVersionSummary[]>;
  onView: (version: number) => void;
  onRestore: (version: number) => Promise<void>;
}

export default function RequestVersionsSheet({
  open,
  onOpenChange,
  docNumber,
  load,
  onView,
  onRestore,
}: RequestVersionsSheetProps) {
  const [versions, setVersions] = useState<RequestVersionSummary[] | null>(null);
  const [restoring, setRestoring] = useState<number | null>(null);

  const reload = useCallback(() => {
    setVersions(null);
    load()
      .then(setVersions)
      .catch((error) => {
        toast.error(
          error instanceof Error ? error.message : 'Failed to load the history',
        );
        setVersions([]);
      });
  }, [load]);

  useEffect(() => {
    if (open) reload();
  }, [open, reload]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>History / {docNumber}</SheetTitle>
          {/* Radix wants a description on every dialog surface, and a screen
              reader gets nothing without one. */}
          <SheetDescription>
            Every saved version of this design, newest first.
          </SheetDescription>
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
              No versions yet. Saving the design writes the first one.
            </p>
          )}

          {versions?.map((version) => (
            <div
              key={version.version}
              className="flex flex-col gap-2 border-b px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              data-testid={`request-version-${version.version}`}
            >
              <div className="min-w-0">
                <span className="text-sm font-medium">
                  Version {version.version}
                </span>
                <p className="mt-0.5 truncate text-sm text-muted-foreground">
                  {version.commit_message || 'No note'}
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
                  onClick={() => onView(version.version)}
                >
                  <Eye className="size-3.5" />
                  View
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={restoring === version.version}
                  onClick={async () => {
                    setRestoring(version.version);
                    try {
                      await onRestore(version.version);
                      reload();
                    } finally {
                      setRestoring(null);
                    }
                  }}
                >
                  <RotateCcw className="size-3.5" />
                  {restoring === version.version ? 'Restoring...' : 'Restore'}
                </Button>
              </div>
            </div>
          ))}
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}
