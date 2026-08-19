'use client';

import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import {
  FULFILMENT_CLASS_LABEL,
  FULFILMENT_CLASS_ORDER,
  FULFILMENT_FACTOR_ORDER,
  fulfilmentFactorLabel,
} from '../lib/labels';
import { useFulfilmentPriority, useSaveFulfilmentPriority } from '../hooks/usePolicies';

/**
 * The ranking that decides both what goes in a container and which purchase-order line
 * arriving stock is assigned to (AC-H5) - one policy, tuned here. Ranking factors weigh a
 * demand row against its competitors; demand-class weights say how much a project order
 * outranks a retail one; the last three settings are the ladder's horizon and cross-
 * ownership-group borrow caps (PLAN-demo-followups-19aug-ladder-v2.md C1/C2).
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
  const [horizonDays, setHorizonDays] = useState('');
  const [borrowMaxQty, setBorrowMaxQty] = useState('');
  const [borrowMaxPct, setBorrowMaxPct] = useState('');
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

    setHorizonDays(String(data.buy_all_horizon_days));
    setBorrowMaxQty(String(data.cross_group_borrow_max_qty));
    setBorrowMaxPct(String(data.cross_group_borrow_max_pct));
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
        setFormError(`${FULFILMENT_CLASS_LABEL[key]} weight must be 0 or more.`);
        return;
      }
      parsedClasses[key] = value;
    }
    for (const [key, raw] of Object.entries(classWeights)) {
      if (key in parsedClasses) continue;
      const value = Number(raw);
      if (Number.isFinite(value)) parsedClasses[key] = value;
    }

    const horizon = Number(horizonDays);
    if (!Number.isInteger(horizon) || horizon <= 0) {
      setFormError('The Buy-all horizon must be a whole number of days greater than 0.');
      return;
    }
    const maxQty = Number(borrowMaxQty);
    if (!Number.isInteger(maxQty) || maxQty < 0) {
      setFormError('The cross-group borrow quantity cap must be 0 or a whole number more.');
      return;
    }
    const maxPct = Number(borrowMaxPct);
    if (!Number.isFinite(maxPct) || maxPct < 0 || maxPct > 100) {
      setFormError('The cross-group borrow percentage cap must be between 0 and 100.');
      return;
    }
    setFormError(null);
    try {
      await save.mutateAsync({
        factors: parsedFactors,
        demand_class_weights: parsedClasses,
        buy_all_horizon_days: horizon,
        cross_group_borrow_max_qty: maxQty,
        cross_group_borrow_max_pct: maxPct,
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
              No fulfilment priority has been activated yet - the seeded defaults below are
              shown. Save to activate them.
            </AlertDescription>
          </Alert>
        ) : null}

        {isError ? (
          <Alert variant="destructive">
            <AlertDescription>Failed to load the fulfilment priority policy.</AlertDescription>
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
                    <Label htmlFor={`fulfilment-factor-${key}`} className="mb-1 block">
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
                        setFactors((prev) => ({ ...prev, [key]: e.target.value }))
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
                    <Label htmlFor={`fulfilment-class-${key}`} className="mb-1 block">
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
                        setClassWeights((prev) => ({ ...prev, [key]: e.target.value }))
                      }
                    />
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="mb-3 text-sm font-medium">Buy-all horizon &amp; cross-group borrow</h4>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div>
                  <Label htmlFor="fulfilment-horizon" className="mb-1 block">
                    Buy-all horizon (days)
                  </Label>
                  <Input
                    id="fulfilment-horizon"
                    type="number"
                    min={1}
                    inputMode="numeric"
                    value={horizonDays}
                    onChange={(e) => setHorizonDays(e.target.value)}
                  />
                  <p className="mt-1 text-2xs text-muted-foreground">
                    A line due further out than this is Buy all - no stock is touched.
                  </p>
                </div>
                <div>
                  <Label htmlFor="fulfilment-borrow-qty" className="mb-1 block">
                    Cross-group borrow cap (qty)
                  </Label>
                  <Input
                    id="fulfilment-borrow-qty"
                    type="number"
                    min={0}
                    inputMode="numeric"
                    value={borrowMaxQty}
                    onChange={(e) => setBorrowMaxQty(e.target.value)}
                  />
                  <p className="mt-1 text-2xs text-muted-foreground">
                    Borrowing across ownership groups is only offered under this quantity.
                  </p>
                </div>
                <div>
                  <Label htmlFor="fulfilment-borrow-pct" className="mb-1 block">
                    Cross-group borrow cap (%)
                  </Label>
                  <Input
                    id="fulfilment-borrow-pct"
                    type="number"
                    min={0}
                    max={100}
                    step={0.5}
                    inputMode="decimal"
                    value={borrowMaxPct}
                    onChange={(e) => setBorrowMaxPct(e.target.value)}
                  />
                  <p className="mt-1 text-2xs text-muted-foreground">
                    ...or this share of the line, whichever the ladder applies.
                  </p>
                </div>
              </div>
            </div>
          </>
        )}
      </CardContent>
      <CardFooter className="justify-end">
        <Button onClick={() => void onSave()} disabled={isLoading || save.isPending}>
          {save.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
          Save fulfilment priority
        </Button>
      </CardFooter>
    </Card>
  );
}
