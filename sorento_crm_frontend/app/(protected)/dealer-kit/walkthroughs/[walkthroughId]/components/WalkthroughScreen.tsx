'use client';

import { useEffect, useState } from 'react';
import { AlertCircle, ChevronLeft, ChevronRight, Pencil, Plus, Trash2 } from 'lucide-react';

import { PageHeader } from '@/components/common/PageHeader';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';

import type { WalkthroughStop, WalkthroughStopStatus } from '../../../services/walkthroughService';
import {
  WALKTHROUGHS_QUERY_KEY,
  usePanoramaQuery,
  useRenameWalkthrough,
  useWalkthroughQuery,
} from '../../hooks/useWalkthroughs';
import { WalkthroughNameDialog } from '../../components/WalkthroughNameDialog';
import { AddStopDialog } from './AddStopDialog';
import { PanoramaViewer } from './PanoramaViewer';

const STATUS_LABEL: Record<WalkthroughStopStatus, string> = {
  processing: 'Processing',
  done: 'Done',
  failed: 'Failed',
};

/**
 * The walkthrough: the current stop's panorama, Previous / Next to walk between
 * stops in order, and the stop list underneath. Only finished stops are walked
 * through; the list shows every stop with its status.
 */
export function WalkthroughScreen({ walkthroughId }: { walkthroughId: string }) {
  const { data, isLoading, isError, error } = useWalkthroughQuery(walkthroughId);
  const rename = useRenameWalkthrough(walkthroughId);
  const [renameOpen, setRenameOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const deletion = useDeferredRowAction({
    actionKey: 'dk_walkthrough_stop.delete',
    entityType: 'dk_walkthrough_stop',
    successMessage: 'Stop deleted',
    invalidateKeys: [[WALKTHROUGHS_QUERY_KEY]],
  });

  const ready = (data?.stops ?? []).filter((stop) => stop.status === 'done');
  const index = Math.max(
    0,
    ready.findIndex((stop) => stop.id === currentId),
  );
  const current: WalkthroughStop | null = ready[index] ?? null;

  // Land on the first finished stop, and move off one that was deleted.
  useEffect(() => {
    if (current && current.id !== currentId) setCurrentId(current.id);
  }, [current, currentId]);

  const panorama = usePanoramaQuery(walkthroughId, current);

  const header = (
    <PageHeader
      title={data?.name ?? 'Showroom Walkthrough'}
      actions={
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            aria-label="Rename walkthrough"
            disabled={!data}
            onClick={() => setRenameOpen(true)}
          >
            <Pencil className="size-4" />
          </Button>
          <Button size="sm" disabled={!data} onClick={() => setAddOpen(true)}>
            <Plus className="size-4" />
            Add stop
          </Button>
        </div>
      }
    />
  );

  if (isError) {
    return (
      <>
        {header}
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertTitle>Could not load this walkthrough</AlertTitle>
          <AlertDescription>
            {error instanceof Error ? error.message : 'Something went wrong. Try again.'}
          </AlertDescription>
        </Alert>
      </>
    );
  }

  return (
    <>
      {header}

      <div className="space-y-5">
        {isLoading ? (
          <Skeleton className="h-[60vh] w-full rounded-lg" />
        ) : current ? (
          <section aria-label="Panorama" className="space-y-3">
            {panorama.data ? (
              <PanoramaViewer
                image={panorama.data}
                hFovDeg={current.hFovDeg ?? 360}
                vFovDeg={current.vFovDeg ?? 180}
                label={current.title}
              />
            ) : panorama.isError ? (
              <Alert variant="destructive">
                <AlertCircle className="size-4" />
                <AlertTitle>Could not load this stop</AlertTitle>
                <AlertDescription>
                  {panorama.error instanceof Error ? panorama.error.message : 'Try again.'}
                </AlertDescription>
              </Alert>
            ) : (
              <Skeleton className="h-[60vh] w-full rounded-lg" />
            )}
            <div className="flex items-center justify-between gap-3">
              <Button
                variant="outline"
                size="sm"
                disabled={index === 0}
                onClick={() => setCurrentId(ready[index - 1]?.id ?? null)}
              >
                <ChevronLeft className="size-4" />
                Previous
              </Button>
              <p className="min-w-0 truncate text-sm font-medium" title={current.title}>
                {index + 1} of {ready.length}: {current.title}
              </p>
              <Button
                variant="outline"
                size="sm"
                disabled={index >= ready.length - 1}
                onClick={() => setCurrentId(ready[index + 1]?.id ?? null)}
              >
                Next
                <ChevronRight className="size-4" />
              </Button>
            </div>
          </section>
        ) : null}

        <Card>
          <CardContent className="p-0">
            <h2 className="border-b px-5 py-3 text-sm font-semibold">Stops</h2>
            {!isLoading && (data?.stops.length ?? 0) === 0 ? (
              <div className="px-5 py-8 text-center" data-testid="dk-wt-stops-empty">
                <p className="text-sm font-medium">No stops yet</p>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  Each stop is one spot in the showroom, added in the order a visitor walks.
                </p>
              </div>
            ) : (
              <ul className="divide-y">
                {(data?.stops ?? []).map((stop) => (
                  <li
                    key={stop.id}
                    className={`flex items-center gap-3 px-5 py-3 ${
                      stop.id === current?.id ? 'bg-muted/50' : ''
                    } ${deletion.targetId === stop.id ? 'opacity-50' : ''}`}
                  >
                    <span className="w-6 shrink-0 text-sm text-muted-foreground">
                      {stop.position}
                    </span>
                    <button
                      type="button"
                      className="min-w-0 flex-1 truncate text-left text-sm font-medium disabled:cursor-default"
                      title={stop.title}
                      disabled={stop.status !== 'done'}
                      onClick={() => setCurrentId(stop.id)}
                    >
                      {stop.title}
                    </button>
                    <div className="flex min-w-0 max-w-[50%] items-center gap-2">
                      <span className={`${STATUS_PILL_BASE} shrink-0 ${statusPillClass(stop.status)}`}>
                        {STATUS_LABEL[stop.status]}
                      </span>
                      {stop.status === 'failed' && stop.errorMessage && (
                        <span
                          className="truncate text-xs text-muted-foreground"
                          title={stop.errorMessage}
                        >
                          {stop.errorMessage}
                        </span>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Delete ${stop.title}`}
                      onClick={() => deletion.run({ id: stop.id, subject: stop.title })}
                    >
                      <Trash2 className="size-4 text-destructive" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        {deletion.countdown}
      </div>

      <AddStopDialog walkthroughId={walkthroughId} open={addOpen} onOpenChange={setAddOpen} />
      <WalkthroughNameDialog
        open={renameOpen}
        onOpenChange={setRenameOpen}
        title="Rename walkthrough"
        submitLabel="Save"
        initialName={data?.name ?? ''}
        isPending={rename.isPending}
        onSubmit={(name) => rename.mutate(name, { onSuccess: () => setRenameOpen(false) })}
      />
    </>
  );
}
