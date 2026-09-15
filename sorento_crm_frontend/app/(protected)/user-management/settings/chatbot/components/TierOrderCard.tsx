'use client';

import { useEffect, useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import OrderableList from '@/components/common/OrderableList';
import { useChatbotTierOrder, useSaveChatbotTierOrder } from '../hooks/useChatbotMemoryAndTierOrder';

const TIER_LABELS: Record<string, string> = {
  dealer: 'Dealer',
  office: 'Office',
  end_user: 'End user',
};

/**
 * Settings > Chatbot > Tier order card (chatbot turn re-architecture, AC-1513, AC-1561, S5).
 *
 * One list, backed by `system_settings.chatbot_tier_order` - today three copies of
 * `TIER_ORDER` in code (AC-1594 deletes them once this is the only source). Saved
 * independently of the Switches card's Save button (its own PUT /settings/general call,
 * a partial body).
 */
export default function TierOrderCard() {
  const query = useChatbotTierOrder();
  const save = useSaveChatbotTierOrder();
  const [draft, setDraft] = useState<string[] | null>(null);

  useEffect(() => {
    if (query.data && draft === null) setDraft(query.data);
  }, [query.data, draft]);

  if (query.isError && !draft) {
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

  if (query.isLoading || !draft) {
    return <Skeleton className="h-56 w-full" />;
  }

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Tier order</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 py-5">
        <OrderableList items={draft} labelFor={(code) => TIER_LABELS[code] ?? code} onChange={setDraft} />
        <p className="text-xs text-muted-foreground">One list. Today three copies in code.</p>
        <div className="flex justify-end">
          <Button
            type="button"
            size="sm"
            disabled={save.isPending}
            onClick={() => draft && save.mutate(draft, { onSuccess: (saved) => setDraft(saved) })}
          >
            {save.isPending && <LoaderCircleIcon className="size-4 animate-spin" />}
            Save
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
