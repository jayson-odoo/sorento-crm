'use client';

import Link from 'next/link';
import { AlertCircle, ExternalLink } from 'lucide-react';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { EM_DASH } from '../../lib/format';
import { useScenarioDiff } from '../hooks/useSimulation';
import type { ScenarioStatus } from '../types/simulation.types';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';

const STATUS_PILL_CODE: Record<ScenarioStatus, string> = {
  SAME: 'new',
  CHANGED: 'pending',
  NEW: 'approved',
  GONE: 'rejected',
  NO_BASELINE: 'voided',
};

const STATUS_LABEL: Record<ScenarioStatus, string> = {
  SAME: 'Same',
  CHANGED: 'Changed',
  NEW: 'New',
  GONE: 'Gone',
  NO_BASELINE: 'No baseline',
};

function fmtDiffValue(v: unknown): string {
  if (v === null || v === undefined) return EM_DASH;
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

export interface ScenarioDiffSheetProps {
  code: string | null;
  onOpenChange: (open: boolean) => void;
  /** Is THIS backend process connected to the dedicated sim database - if so, the
   *  Reorder Planning page (opened by the link below) shows the sim world's own latest
   *  run automatically (it always opens to "today's plan, or the latest completed run" -
   *  there is no per-run deep link to pass a specific run id). */
  simDbActive?: boolean;
}

export function ScenarioDiffSheet({ code, onOpenChange, simDbActive = false }: ScenarioDiffSheetProps) {
  const { data, isLoading, isError, error } = useScenarioDiff(code);

  return (
    <Sheet open={code !== null} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl"
        aria-describedby={undefined}
      >
        <SheetHeader className="border-b p-4 pe-12 sm:p-6 sm:pe-12">
          <SheetTitle className="break-words">
            {code}
            {data ? (
              <span className="ms-2 text-sm font-normal text-muted-foreground">
                {(data.current?.title as string | undefined) ??
                  (data.baseline?.title as string | undefined) ??
                  ''}
              </span>
            ) : null}
          </SheetTitle>
          <SheetDescription>
            {data ? (
              <span className={`${STATUS_PILL_BASE} ${statusPillClass(STATUS_PILL_CODE[data.status])}`}>
                {STATUS_LABEL[data.status]}
              </span>
            ) : (
              'Loading...'
            )}
          </SheetDescription>
        </SheetHeader>

        <SheetBody className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-3/4" />
            </div>
          ) : null}

          {isError ? (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <span>{error?.message ?? 'Failed to load this scenario.'}</span>
            </div>
          ) : null}

          {data ? (
            <>
              <section>
                <h4 className="mb-2 text-2xs font-medium uppercase text-muted-foreground">
                  Field-level diff vs the blessed baseline
                </h4>
                {data.diffs.length === 0 ? (
                  <p className="text-2xs text-muted-foreground">
                    {data.status === 'NO_BASELINE'
                      ? 'No baseline has been blessed yet, so there is nothing to compare against.'
                      : 'Nothing differs from the blessed baseline.'}
                  </p>
                ) : (
                  <div className="overflow-hidden rounded-lg border">
                    <ScrollArea>
                      <table className="w-auto min-w-full text-2xs">
                        <thead className="bg-muted/40 text-muted-foreground">
                          <tr>
                            <th className="px-2 py-1.5 text-start font-medium">Group</th>
                            <th className="px-2 py-1.5 text-start font-medium">Field</th>
                            <th className="px-2 py-1.5 text-start font-medium">Baseline</th>
                            <th className="px-2 py-1.5 text-start font-medium">Current</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.diffs.map((d) => (
                            <tr key={d.path} className="border-t">
                              <td className="px-2 py-1.5 text-muted-foreground">{d.group}</td>
                              <td className="max-w-40 truncate px-2 py-1.5 font-mono" title={d.path}>
                                {d.path}
                              </td>
                              <td className="max-w-32 truncate px-2 py-1.5" title={fmtDiffValue(d.old)}>
                                {fmtDiffValue(d.old)}
                              </td>
                              <td className="max-w-32 truncate px-2 py-1.5 font-medium" title={fmtDiffValue(d.new)}>
                                {fmtDiffValue(d.new)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <ScrollBar orientation="horizontal" />
                    </ScrollArea>
                  </div>
                )}
              </section>

              <section>
                <h4 className="mb-2 text-2xs font-medium uppercase text-muted-foreground">
                  Frozen inputs (the current snapshot the engine saw)
                </h4>
                {data.current ? (
                  <pre className="max-h-80 overflow-auto rounded-lg border bg-muted/20 p-3 text-2xs">
                    {JSON.stringify(data.current, null, 2)}
                  </pre>
                ) : (
                  <p className="text-2xs text-muted-foreground">
                    No run has covered this scenario yet.
                  </p>
                )}
              </section>
            </>
          ) : null}
        </SheetBody>

        <SheetFooter className="flex-row justify-between gap-2 border-t p-4 sm:p-6">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button
            variant="outline"
            asChild
            title={
              simDbActive
                ? 'Reorder Planning opens to its latest run - this sim database has only one.'
                : 'This backend is not on the sim database - Reorder Planning will show whatever this process is actually connected to.'
            }
          >
            <Link href="/scm/reorder">
              Open in planning
              <ExternalLink className="size-3.5" />
            </Link>
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

export default ScenarioDiffSheet;
