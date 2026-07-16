'use client';

import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useSaveSupplierScoring, useSupplierScoring } from '../hooks/usePolicies';

/**
 * Global supplier-scoring weights (single row). Delivery + Quality weights blend
 * into each supplier's composite score and MUST sum to 100%. Consumed by the
 * ANALYTICS job, so edits take effect on the next analytics run.
 */
export function SupplierScoringPanel() {
  const { data, isLoading, isError } = useSupplierScoring();
  const save = useSaveSupplierScoring();

  const [delivery, setDelivery] = useState('');
  const [quality, setQuality] = useState('');
  const [grace, setGrace] = useState('');
  const [minSample, setMinSample] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!data) return;
    setDelivery(String(Math.round(data.delivery_weight * 100)));
    setQuality(String(Math.round(data.quality_weight * 100)));
    setGrace(String(data.grace_days));
    setMinSample(String(data.min_sample_size));
  }, [data]);

  const deliveryNum = Number(delivery);
  const qualityNum = Number(quality);
  const weightSum =
    Number.isFinite(deliveryNum) && Number.isFinite(qualityNum) ? deliveryNum + qualityNum : NaN;
  const sumOk = Math.abs(weightSum - 100) < 0.1;

  const onSave = async () => {
    if (!(deliveryNum >= 0 && deliveryNum <= 100) || !(qualityNum >= 0 && qualityNum <= 100)) {
      setFormError('Each weight must be between 0 and 100%.');
      return;
    }
    if (!sumOk) {
      setFormError('Delivery and quality weights must add up to 100%.');
      return;
    }
    const graceNum = Number(grace);
    const minSampleNum = Number(minSample);
    if (!(graceNum >= 0)) {
      setFormError('On-time grace must be 0 or more days.');
      return;
    }
    if (!(Number.isInteger(minSampleNum) && minSampleNum >= 1)) {
      setFormError('Minimum sample size must be a whole number of 1 or more.');
      return;
    }
    setFormError(null);
    await save.mutateAsync({
      delivery_weight: deliveryNum / 100,
      quality_weight: qualityNum / 100,
      grace_days: graceNum,
      min_sample_size: minSampleNum,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle>Supplier scoring</CardTitle>
        </CardHeading>
      </CardHeader>
      <CardContent className="space-y-5">
        <p className="text-sm text-muted-foreground">
          Each supplier gets a composite performance score that blends how reliably they deliver{' '}
          <strong>on time</strong> with their <strong>quality</strong> (accepted vs rejected
          receipts). The two weights set how much each matters and must total 100%.
        </p>

        {!data?.exists && !isLoading ? (
          <Alert>
            <AlertDescription>
              No scoring policy saved yet — the seeded defaults below are shown. Save to store them.
            </AlertDescription>
          </Alert>
        ) : null}

        {isError ? (
          <Alert variant="destructive">
            <AlertDescription>Failed to load supplier scoring.</AlertDescription>
          </Alert>
        ) : null}

        {formError ? (
          <Alert variant="destructive">
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        ) : null}

        {isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <Label className="mb-1 block">Delivery weight (%)</Label>
                <Input type="number" min={0} max={100} inputMode="numeric" value={delivery} onChange={(e) => setDelivery(e.target.value)} />
                <p className="mt-1 text-2xs text-muted-foreground">How much on-time delivery counts.</p>
              </div>
              <div>
                <Label className="mb-1 block">Quality weight (%)</Label>
                <Input type="number" min={0} max={100} inputMode="numeric" value={quality} onChange={(e) => setQuality(e.target.value)} />
                <p className="mt-1 text-2xs text-muted-foreground">How much receipt quality counts.</p>
              </div>
            </div>

            <div
              className={cn(
                'flex items-center justify-between rounded-md border px-3 py-2 text-sm',
                sumOk ? 'border-border bg-muted/30 text-muted-foreground' : 'border-destructive/40 bg-destructive/5 text-destructive',
              )}
            >
              <span>Weights total</span>
              <span className="font-semibold tabular-nums">
                {Number.isFinite(weightSum) ? `${weightSum}%` : '—'}
                {!sumOk ? ' (must be 100%)' : ''}
              </span>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <Label className="mb-1 block">On-time grace (days)</Label>
                <Input type="number" min={0} inputMode="numeric" value={grace} onChange={(e) => setGrace(e.target.value)} />
                <p className="mt-1 text-2xs text-muted-foreground">
                  A delivery this many days late still counts as on time.
                </p>
              </div>
              <div>
                <Label className="mb-1 block">Minimum sample size</Label>
                <Input type="number" min={1} inputMode="numeric" value={minSample} onChange={(e) => setMinSample(e.target.value)} />
                <p className="mt-1 text-2xs text-muted-foreground">
                  How many receipts a supplier needs before their score is trusted.
                </p>
              </div>
            </div>
          </>
        )}

        <p className="rounded-md bg-muted/40 px-3 py-2 text-2xs text-muted-foreground">
          Takes effect on the next analytics run, which recomputes supplier scores.
        </p>
      </CardContent>
      <CardFooter className="justify-end">
        <Button onClick={() => void onSave()} disabled={isLoading || save.isPending || !sumOk}>
          {save.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
          Save scoring
        </Button>
      </CardFooter>
    </Card>
  );
}
