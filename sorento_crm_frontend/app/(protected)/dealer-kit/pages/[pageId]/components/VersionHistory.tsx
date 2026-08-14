'use client';

import { useState } from 'react';
import { History, Undo2 } from 'lucide-react';

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
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { PageVersion } from '@/lib/dealer-kit/types';

/**
 * Version history. Publishing and rolling back are the SAME operation - moving
 * the `published` label to a different version - so rollback costs nothing and
 * loses nothing. No version row is ever rewritten.
 */
export function VersionHistory({
  versions,
  onPublish,
}: {
  versions: PageVersion[];
  onPublish: (versionId: string) => void | Promise<void>;
}) {
  const [rollbackTarget, setRollbackTarget] = useState<PageVersion | null>(null);
  const liveVersion = versions.find((version) => version.labels.includes('published'));

  if (versions.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center">
          <History className="mx-auto size-5 text-muted-foreground" />
          <p className="mt-2 text-sm font-medium text-foreground">No versions yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Saving this page creates version 1. Publishing then points the live address at it.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Version history</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border p-0">
          {versions.map((version) => {
            const isLive = version.labels.includes('published');
            const isOlderThanLive = Boolean(liveVersion && version.version < liveVersion.version);

            return (
              <div
                key={version.id}
                className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">Version {version.version}</span>
                    {isLive && (
                      <Badge variant="success" appearance="ghost" className="font-normal">
                        Live
                      </Badge>
                    )}
                    {version.labels.includes('staging') && (
                      <Badge variant="outline" appearance="ghost" className="font-normal">
                        Staging
                      </Badge>
                    )}
                  </div>
                  <p className="mt-0.5 truncate text-sm text-muted-foreground">
                    {version.commitMessage || 'No description'}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {version.createdBy} · {formatDateTimeInMalaysia(version.createdAt)}
                  </p>
                </div>

                {!isLive && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0"
                    onClick={() =>
                      isOlderThanLive ? setRollbackTarget(version) : onPublish(version.id)
                    }
                  >
                    {isOlderThanLive && <Undo2 className="size-3.5" />}
                    {isOlderThanLive ? 'Roll back to this' : 'Publish this'}
                  </Button>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>

      <AlertDialog
        open={Boolean(rollbackTarget)}
        onOpenChange={(open) => !open && setRollbackTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Roll back the live catalogue?</AlertDialogTitle>
            <AlertDialogDescription>
              Everyone reading the public address will immediately see version{' '}
              {rollbackTarget?.version} instead of version {liveVersion?.version}. Both versions
              are kept, so this can be moved back again.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (rollbackTarget) onPublish(rollbackTarget.id);
                setRollbackTarget(null);
              }}
            >
              Roll back
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
