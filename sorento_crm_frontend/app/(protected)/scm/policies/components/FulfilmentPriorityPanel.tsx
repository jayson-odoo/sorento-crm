'use client';

import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardHeading,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import {
  FULFILMENT_CLASS_LABEL,
  FULFILMENT_CLASS_ORDER,
  FULFILMENT_FACTOR_ORDER,
  fulfilmentFactorLabel,
} from '../lib/labels';
import { DEFAULT_TBA_DATE_FROM } from '../types/policy.types';
import {
  useFulfilmentPriority,
  useSaveFulfilmentPriority,
} from '../hooks/usePolicies';

/** Local calendar day as `YYYY-MM-DD`, so the mirror of the backend check reads the same
 *  date the user sees in the picker rather than a UTC-shifted one. */
function todayIso(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 10);
}

/**
 * The ranking that decides both what goes in a container and which purchase-order line
 * arriving stock is assigned to (AC-H5) - one policy, tuned here. Ranking factors weigh a
 * demand row against its competitors; demand-class weights say how much a project order
 * outranks a retail one; the last two settings are the ladder's two calendar dates.
 *
 * `reorder_coverage_until` is a CALENDAR DATE (19 Aug follow-up), not a rolling day count -
 * the captain's own framing was "purchasing reorders until October". A line required after
 * this date is proposed as Buy now, untouched; clearing it means no coverage limit is set.
 *
 * `tba_date_from` is the other end of the same idea (borrow ladder v7.1, R20): demand dated
 * on or after it is TBA - it takes no supply, is never covered and never donates. It is NOT
 * NULL, so the button beside it resets to the column default rather than emptying the field.
 * The cross-group borrow caps that used to sit here are gone with R5: any ownership group may
 * donate now, so there is nothing left for a cap to cap.
 *
 * Read and edit are the same layout - every value is always an input, the way the other
 * policy panels on this page already work; Save writes a NEW policy revision and activates
 * it, so the ranking history a planner was judged against is never rewritten in place.
 */
export function FulfilmentPriorityPanel() {
  const { data, isLoading, isError } = useFulfilmentPriority();
  const save = useSaveFulfilmentPriority();

  const [factors, setFactors] = useState<Record<string, string>>({});
  const [classWeights, setClassWeights] = useState<Record<string, string>>({});
  const [reorderCoverageUntil, setReorderCoverageUntil] = useState('');
  const [tbaDateFrom, setTbaDateFrom] = useState('');
  const [transferDays, setTransferDays] = useState('0');
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    // Seeded from the FULL stored record, not just the keys this screen renders: the
    // backend keeps `factors` / `demand_class_weights` as open JSONB precisely so a
    // policy can carry a factor this UI does not yet know about, and a draft that only
    // remembered the rendered keys would drop it the moment it was saved again.
    const nextFactors: Record<string, string> = {};
    for (const [key, value] of Object.entries(data.factors)) {
      nextFactors[key] = String(value);
    }
    for (const key of FULFILMENT_FACTOR_ORDER) {
      if (!(key in nextFactors)) nextFactors[key] = '0';
    }
    setFactors(nextFactors);

    const nextClasses: Record<string, string> = {};
    for (const [key, value] of Object.entries(data.demand_class_weights)) {
      nextClasses[key] = String(value);
    }
    for (const key of FULFILMENT_CLASS_ORDER) {
      if (!(key in nextClasses)) nextClasses[key] = '0';
    }
    setClassWeights(nextClasses);

    setReorderCoverageUntil(data.reorder_coverage_until ?? '');
    setTbaDateFrom(data.tba_date_from);
    setTransferDays(String(data.transfer_days ?? 0));
  }, [data]);

  const onSave = async () => {
    const parsedFactors: Record<string, number> = {};
    for (const key of FULFILMENT_FACTOR_ORDER) {
      const value = Number(factors[key]);
      if (!Number.isFinite(value) || value < 0) {
        setFormError(`${fulfilmentFactorLabel(key)} weight must be 0 or more.`);
        return;
      }
      parsedFactors[key] = value;
    }
    // Any factor the stored policy carries beyond what this screen renders travels
    // through untouched, merged over the edited set rather than replacing it.
    for (const [key, raw] of Object.entries(factors)) {
      if (key in parsedFactors) continue;
      const value = Number(raw);
      if (Number.isFinite(value)) parsedFactors[key] = value;
    }

    const parsedClasses: Record<string, number> = {};
    for (const key of FULFILMENT_CLASS_ORDER) {
      const value = Number(classWeights[key]);
      if (!Number.isFinite(value) || value < 0) {
        setFormError(
          `${FULFILMENT_CLASS_LABEL[key]} weight must be 0 or more.`,
        );
        return;
      }
      parsedClasses[key] = value;
    }
    for (const [key, raw] of Object.entries(classWeights)) {
      if (key in parsedClasses) continue;
      const value = Number(raw);
      if (Number.isFinite(value)) parsedClasses[key] = value;
    }

    // A native date input hands back '' when the user clears it, and the column is NOT
    // NULL - so an emptied field saves the default rather than nothing. This is the ONE
    // fallback on this screen: what the backend sends is rendered as it comes.
    const tba = tbaDateFrom || DEFAULT_TBA_DATE_FROM;
    // The backend rejects a CHANGE to a past TBA date with 422; mirrored here so the
    // message arrives beside the field instead of as a toast after a round trip.
    //
    // Only when the field is DIRTY. Every save sends the whole record, so once a
    // configured date had quietly passed this check refused the panel's own unchanged
    // value - and with it every weight, coverage date and class weight on the screen. The
    // rule is about moving the TBA line back, not about the age of a date nobody touched.
    if (tba !== data?.tba_date_from && tba < todayIso()) {
      setFormError('TBA date from must be today or later.');
      return;
    }

    // R-B (31 Aug ruling): 0 by default, and never negative - the backend's own
    // `transfer_days_negative` coded 422 mirrored here so the message sits beside the
    // field instead of arriving as a toast after a round trip.
    const parsedTransferDays = Number(transferDays);
    if (!Number.isFinite(parsedTransferDays) || parsedTransferDays < 0) {
      setFormError('Transfer days between bins must be 0 or more.');
      return;
    }

    setFormError(null);
    try {
      await save.mutateAsync({
        factors: parsedFactors,
        demand_class_weights: parsedClasses,
        reorder_coverage_until: reorderCoverageUntil || null,
        tba_date_from: tba,
        transfer_days: Math.trunc(parsedTransferDays),
      });
    } catch {
      // Already toasted by the mutation's own onError; this only stops the rejection
      // `mutateAsync` rethrows from reaching the click handler unhandled.
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle>Fulfilment priority</CardTitle>
        </CardHeading>
      </CardHeader>
      <CardContent className="space-y-6">
        {!data?.exists && !isLoading ? (
          <Alert>
            <AlertDescription>
              No fulfilment priority has been activated yet - the seeded
              defaults below are shown. Save to activate them.
            </AlertDescription>
          </Alert>
        ) : null}

        {isError ? (
          <Alert variant="destructive">
            <AlertDescription>
              Failed to load the fulfilment priority policy.
            </AlertDescription>
          </Alert>
        ) : null}

        {formError ? (
          <Alert variant="destructive">
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        ) : null}

        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : (
          <>
            <div>
              <h4 className="mb-3 text-sm font-medium">Ranking factors</h4>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {FULFILMENT_FACTOR_ORDER.map((key) => (
                  <div key={key}>
                    <Label
                      htmlFor={`fulfilment-factor-${key}`}
                      className="mb-1 block"
                    >
                      {fulfilmentFactorLabel(key)}
                    </Label>
                    <Input
                      id={`fulfilment-factor-${key}`}
                      type="number"
                      min={0}
                      max={10}
                      step={0.5}
                      inputMode="decimal"
                      value={factors[key] ?? ''}
                      onChange={(e) =>
                        setFactors((prev) => ({
                          ...prev,
                          [key]: e.target.value,
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="mb-3 text-sm font-medium">Demand class weight</h4>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {FULFILMENT_CLASS_ORDER.map((key) => (
                  <div key={key}>
                    <Label
                      htmlFor={`fulfilment-class-${key}`}
                      className="mb-1 block"
                    >
                      {FULFILMENT_CLASS_LABEL[key]}
                    </Label>
                    <Input
                      id={`fulfilment-class-${key}`}
                      type="number"
                      min={0}
                      max={10}
                      step={0.5}
                      inputMode="decimal"
                      value={classWeights[key] ?? ''}
                      onChange={(e) =>
                        setClassWeights((prev) => ({
                          ...prev,
                          [key]: e.target.value,
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="mb-3 text-sm font-medium">Coverage dates</h4>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <Label
                    htmlFor="fulfilment-coverage-until"
                    className="mb-1 block"
                  >
                    Purchasing covers demand until
                  </Label>
                  <div className="flex items-center gap-2">
                    <Input
                      id="fulfilment-coverage-until"
                      type="date"
                      value={reorderCoverageUntil}
                      onChange={(e) => setReorderCoverageUntil(e.target.value)}
                      className="w-full"
                    />
                    {reorderCoverageUntil ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setReorderCoverageUntil('')}
                      >
                        Clear
                      </Button>
                    ) : null}
                  </div>
                  <p className="mt-1 text-2xs text-muted-foreground">
                    Lines required after this date are proposed as Buy now.
                  </p>
                </div>
                <div>
                  <Label
                    htmlFor="fulfilment-tba-date-from"
                    className="mb-1 block"
                  >
                    TBA date from
                  </Label>
                  <div className="flex items-center gap-2">
                    <Input
                      id="fulfilment-tba-date-from"
                      type="date"
                      value={tbaDateFrom}
                      onChange={(e) => setTbaDateFrom(e.target.value)}
                      className="w-full"
                    />
                    {tbaDateFrom !== DEFAULT_TBA_DATE_FROM ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setTbaDateFrom(DEFAULT_TBA_DATE_FROM)}
                      >
                        Reset
                      </Button>
                    ) : null}
                  </div>
                </div>
              </div>
            </div>

            <div>
              <h4 className="mb-3 text-sm font-medium">Transfer cost</h4>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <Label
                    htmlFor="fulfilment-transfer-days"
                    className="mb-1 block"
                  >
                    Transfer days between bins
                  </Label>
                  <Input
                    id="fulfilment-transfer-days"
                    type="number"
                    min={0}
                    step={1}
                    inputMode="numeric"
                    value={transferDays}
                    onChange={(e) => setTransferDays(e.target.value)}
                    className="w-full"
                  />
                  <p className="mt-1 text-2xs text-muted-foreground">
                    Added to a non-own-location option's fulfil date. 0 charges
                    nothing.
                  </p>
                </div>
              </div>
            </div>
          </>
        )}
      </CardContent>
      <CardFooter className="justify-end">
        <Button
          onClick={() => void onSave()}
          disabled={isLoading || save.isPending}
        >
          {save.isPending ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : null}
          Save fulfilment priority
        </Button>
      </CardFooter>
    </Card>
  );
}
