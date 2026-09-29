'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import {
  useCostPriceVerificationSetting,
  useUpdateCostPriceVerificationSetting,
} from '../hooks/useCostPriceVerificationSetting';

/**
 * "Verify cost price uploads by a second person" (#1288, AC-S2-16), off by default. Its own
 * card rather than a field in the General form: the review page (Purchasing > Cost Price
 * Uploads) reads this same flag to decide whether it shows Submit/Decide/Return or a plain
 * Apply, so flipping it has an effect elsewhere in the app the moment it saves - worth its
 * own save button rather than waiting on the General form's.
 */
export function CostPriceVerificationCard() {
  const { data, isLoading } = useCostPriceVerificationSetting();
  const update = useUpdateCostPriceVerificationSetting();

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Purchasing</CardTitle>
      </CardHeader>
      <CardContent className="py-6">
        {isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <div className="flex items-center gap-4 rounded-lg bg-accent/60 p-4">
            <div className="flex-1 space-y-1">
              <Label htmlFor="cost-price-verification-enabled">
                Verify cost price uploads by a second person
              </Label>
              <p className="text-sm text-muted-foreground">
                Off: the uploader applies a staff upload directly. A supplier&apos;s own
                submission always waits for a Sorento verifier, whatever this setting.
              </p>
            </div>
            <Switch
              id="cost-price-verification-enabled"
              checked={Boolean(data?.enabled)}
              disabled={update.isPending}
              onCheckedChange={(checked) => update.mutate(checked)}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default CostPriceVerificationCard;
