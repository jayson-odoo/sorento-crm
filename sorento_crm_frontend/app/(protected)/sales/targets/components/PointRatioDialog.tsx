'use client';

import { Fragment, useState } from 'react';
import { Check, Pencil, Trash2, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DatePicker } from '@/components/ui/date-picker';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { NumberInput } from '@/components/ui/number-input';
import { Label } from '@/components/ui/label';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import {
  formatLocalDateToYyyyMmDd,
  todayMalaysiaYyyyMmDd,
} from '@/lib/helpers';
import {
  POINT_RATIOS_KEY,
  SALES_TARGET_KEY,
  SALES_TARGETS_KEY,
  usePointRatios,
  useSavePointRatio,
  useUpdatePointRatio,
} from '../hooks/useSalesTargets';
import { formatFigure, shortDate } from '../lib/format';

/**
 * RM per point, a dated history for the acting company (owner ruling 5, Q4; mock frame E). A
 * period uses the ratio in force on its last day; the same date again replaces that date's ratio.
 *
 * Each row edits in place (lane POINT-RATIO-EDIT) and deletes as a deferred action with an inline
 * countdown (D7, the CostRowDialog shape): the older ratio then applies from that date on.
 */

interface RowDraft {
  id: string;
  ratio: string;
  from: string;
}

/** A civil date: noon keeps it on the same day in any time zone. */
const civil = (day: string) => (day ? new Date(`${day}T12:00:00`) : undefined);

function validRatio(raw: string) {
  const n = Number(raw);
  return raw.trim() !== '' && Number.isFinite(n) && n > 0;
}
export default function PointRatioDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { data, isLoading } = usePointRatios(open);
  const save = useSavePointRatio();
  const update = useUpdatePointRatio();
  const [ratio, setRatio] = useState('');
  const [from, setFrom] = useState(() => todayMalaysiaYyyyMmDd());
  const [draft, setDraft] = useState<RowDraft | null>(null);
  const value = Number(ratio);
  const canAdd = validRatio(ratio) && !!from && !save.isPending;
  const canSaveRow =
    !!draft && validRatio(draft.ratio) && !!draft.from && !update.isPending;
  const rows = data?.rows ?? [];
  const deletion = useDeferredRowAction({
    actionKey: 'point_ratio.delete',
    entityType: 'point_ratio',
    surface: 'inline',
    // Its own full-width line under the row (below), so Cancel stays on screen at 375px.
    countdownClassName: 'w-full min-w-0',
    successMessage: 'Ratio deleted.',
    invalidateKeys: [
      [...POINT_RATIOS_KEY],
      [...SALES_TARGETS_KEY],
      [...SALES_TARGET_KEY],
    ],
  });

  const saveRow = async () => {
    if (!draft || !canSaveRow) return;
    try {
      await update.mutateAsync({
        id: draft.id,
        effective_from: draft.from,
        rm_per_point: Number(draft.ratio),
      });
      setDraft(null);
    } catch {
      // The hook toasted the reason; the row stays open to fix it.
    }
  };

  const add = async () => {
    if (!canAdd) return;
    try {
      await save.mutateAsync({ effective_from: from, rm_per_point: value });
      setRatio('');
    } catch {
      // The hook toasted the reason.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Point ratio</DialogTitle>
          <DialogDescription>RM per point, from a date on.</DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <div className="flex flex-col gap-1">
              <Label
                htmlFor="point-ratio-value"
                className="text-xs text-muted-foreground"
              >
                RM per point
              </Label>
              <NumberInput
                id="point-ratio-value"
                min={0}
                step="any"
                value={ratio}
                onChange={(e) => setRatio(e.target.value)}
                className="h-8"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label
                htmlFor="point-ratio-from"
                className="text-xs text-muted-foreground"
              >
                From
              </Label>
              <DatePicker
                id="point-ratio-from"
                ariaLabel="From"
                portal
                value={civil(from)}
                onChange={(d) => setFrom(d ? formatLocalDateToYyyyMmDd(d) : '')}
              />
            </div>
            <Button size="sm" onClick={() => void add()} disabled={!canAdd}>
              Add
            </Button>
          </div>
          {isLoading ? null : rows.length ? (
            <div className="overflow-x-auto rounded-lg border">
              <table aria-label="Point ratios" className="w-full text-sm">
                <thead className="bg-muted/40 text-xs text-muted-foreground">
                  <tr>
                    <th className="whitespace-nowrap px-3 py-2 text-start font-medium">
                      From
                    </th>
                    <th className="whitespace-nowrap px-3 py-2 text-end font-medium">
                      RM per point
                    </th>
                    <th className="w-px px-2 py-2">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {rows.map((r) =>
                    draft?.id === r.id ? (
                      <tr key={r.id}>
                        {/* One cell that wraps, so the inputs never clip at 375px; same order as the row. */}
                        <td colSpan={3} className="px-2 py-1.5">
                          <div className="flex flex-wrap items-center gap-2">
                            <DatePicker
                              id={`point-ratio-from-${r.id}`}
                              ariaLabel="Ratio from"
                              portal
                              className="min-w-[9rem] flex-1"
                              value={civil(draft.from)}
                              onChange={(d) =>
                                setDraft({
                                  ...draft,
                                  from: d ? formatLocalDateToYyyyMmDd(d) : '',
                                })
                              }
                            />
                            <NumberInput
                              aria-label="Edit RM per point"
                              min={0}
                              step="any"
                              value={draft.ratio}
                              onChange={(e) =>
                                setDraft({ ...draft, ratio: e.target.value })
                              }
                              className="h-8 w-24 text-end"
                            />
                            <div className="ms-auto flex gap-1">
                              <Button
                                variant="ghost"
                                mode="icon"
                                size="sm"
                                aria-label="Save ratio"
                                disabled={!canSaveRow}
                                onClick={() => void saveRow()}
                              >
                                <Check className="size-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                mode="icon"
                                size="sm"
                                aria-label="Cancel edit"
                                onClick={() => setDraft(null)}
                              >
                                <X className="size-4" />
                              </Button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : deletion.targetId === r.id && deletion.countdown ? (
                      // Counting down: the row dims and its countdown gets a full-width row of its
                      // own, so Cancel is never pushed off screen at 375px.
                      <Fragment key={r.id}>
                        <tr className="text-muted-foreground">
                          <td className="whitespace-nowrap px-3 py-2">
                            {shortDate(r.effective_from)}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-end tabular-nums">
                            {formatFigure(r.rm_per_point)}
                          </td>
                          <td>
                            <span className="sr-only">Deleting</span>
                          </td>
                        </tr>
                        <tr className="!border-t-0">
                          <td colSpan={3} className="px-2 pb-2">
                            {deletion.countdown}
                          </td>
                        </tr>
                      </Fragment>
                    ) : (
                      <tr key={r.id}>
                        <td className="whitespace-nowrap px-3 py-2">
                          {shortDate(r.effective_from)}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 text-end tabular-nums">
                          {formatFigure(r.rm_per_point)}
                        </td>
                        <td className="whitespace-nowrap px-2 py-1">
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost"
                              mode="icon"
                              size="sm"
                              aria-label={`Edit ratio from ${shortDate(r.effective_from)}`}
                              onClick={() =>
                                setDraft({
                                  id: r.id,
                                  ratio: String(r.rm_per_point),
                                  from: r.effective_from,
                                })
                              }
                            >
                              <Pencil className="size-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              mode="icon"
                              size="sm"
                              aria-label={`Delete ratio from ${shortDate(r.effective_from)}`}
                              onClick={() =>
                                deletion.run({
                                  id: r.id,
                                  subject: `the ratio from ${shortDate(r.effective_from)}`,
                                })
                              }
                            >
                              <Trash2 className="size-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-lg border border-dashed py-6 text-center text-sm font-medium">
              No ratio yet
            </div>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
