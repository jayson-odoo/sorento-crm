'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import OrderableList from '@/components/common/OrderableList';

const TIER_LABELS: Record<string, string> = {
  dealer: 'Dealer',
  office: 'Office',
  end_user: 'End user',
};

/**
 * Settings > Chatbot > Tier order card (chatbot turn re-architecture, AC-1513, AC-1561, S5).
 *
 * One list, backed by `system_settings.chatbot_tier_order` - today three copies of
 * `TIER_ORDER` in code (AC-1594 deletes them once this is the only source). CONTROLLED:
 * the page owns the draft and the ONE Save button (browser pass 1, 16 Sep 2026).
 */
export default function TierOrderCard({
  value,
  onChange,
  isLoading,
  isError,
}: {
  value: string[] | null;
  onChange: (next: string[]) => void;
  isLoading: boolean;
  isError: boolean;
}) {
  const draft = value;

  if (isError && !draft) {
    return (
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>Tier order</CardTitle>
        </CardHeader>
        <CardContent className="py-5">
          <p className="text-sm text-destructive">
            Tier order could not be loaded. Reload the page to try again.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (isLoading || !draft) {
    return <Skeleton className="h-56 w-full" />;
  }

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Tier order</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 py-5">
        <OrderableList items={draft} labelFor={(code) => TIER_LABELS[code] ?? code} onChange={onChange} />
      </CardContent>
    </Card>
  );
}
