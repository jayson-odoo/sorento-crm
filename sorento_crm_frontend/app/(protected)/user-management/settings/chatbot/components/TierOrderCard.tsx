'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import OrderableList from '@/components/common/OrderableList';

const TIER_LABELS: Record<string, string> = {
  dealer: 'Dealer',
  office: 'Office',
  end_user: 'End user',
};

/**
 * Settings > Chatbot > Tier order card (chatbot turn re-architecture, AC-1513, M5).
 *
 * One list, backed by `system_settings.chatbot_tier_order` (S5, AC-1561) - today three
 * copies of `TIER_ORDER` in code (AC-1594 deletes them once this is the only source).
 * Controlled: the page's own draft carries the value, saved by the page's single Save
 * button alongside the rest of `ChatbotSettings` - one settings row, one save.
 */
export default function TierOrderCard({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Tier order</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 py-5">
        <OrderableList
          items={value}
          labelFor={(code) => TIER_LABELS[code] ?? code}
          onChange={onChange}
        />
        <p className="text-xs text-muted-foreground">One list. Today three copies in code.</p>
      </CardContent>
    </Card>
  );
}
