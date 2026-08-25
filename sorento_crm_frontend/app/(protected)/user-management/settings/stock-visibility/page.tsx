'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { StockVisibilitySection } from '@/components/stock-visibility/StockVisibilitySection';

/**
 * Settings -> Stock Visibility (PLAN-stock-visibility-policy, S1).
 *
 * The bottom of the resolution chain: what a contact is told about stock when neither
 * it nor any of its access types carries a policy. Flipping this row is also how the
 * legacy per-location list is eventually phased out, so it is one card and one Save.
 */
export default function StockVisibilitySettingsPage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Stock Visibility</CardTitle>
      </CardHeader>
      <CardContent>
        <StockVisibilitySection heading={null} scope={{ kind: 'default' }} />
      </CardContent>
    </Card>
  );
}
