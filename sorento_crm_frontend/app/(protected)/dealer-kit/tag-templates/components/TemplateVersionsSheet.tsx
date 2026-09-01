'use client';

/**
 * Versions sheet: history newest-first, View opens the read-only canvas
 * (D16), Restore copies a version's doc into the draft after a confirm
 * (D15) - it never moves the live pointer, so it and Publish stay two
 * different acts even though both start from the same list.
 */

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Eye, RotateCcw } from 'lucide-react';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
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
  const [restoreTarget, setRestoreTarget] = useState<TagTemplateVersion | null>(null);
  const [restoring, setRestoring] = useState(false);

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
    <>
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
                      onClick={() => setRestoreTarget(version)}
                    >
                      <RotateCcw className="size-3.5" />
                      Restore
                    </Button>
                  </div>
                </div>
              );
            })}
          </SheetBody>
        </SheetContent>
      </Sheet>

      <AlertDialog
        open={Boolean(restoreTarget)}
        onOpenChange={(nextOpen) => !nextOpen && !restoring && setRestoreTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Restore version {restoreTarget?.version_no}?</AlertDialogTitle>
            <AlertDialogDescription>
              This replaces the current draft with version {restoreTarget?.version_no}&apos;s
              design. Unsaved draft changes are lost. The live published version is not
              affected until you Publish again.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={restoring}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={restoring}
              onClick={async (e) => {
                e.preventDefault();
                if (!restoreTarget) return;
                setRestoring(true);
                try {
                  await onRestore(restoreTarget.id);
                  setRestoreTarget(null);
                  onOpenChange(false);
                } finally {
                  setRestoring(false);
                }
              }}
            >
              {restoring ? 'Restoring...' : 'Restore'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
