'use client';

import type { ChangeEvent } from 'react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

/**
 * Settings > Chatbot > Stock low threshold card (S0, AC-1732, AC-1733; D7).
 *
 * Controlled, presentational only: `chatbot_stock_low_threshold_pct` is a field of the
 * SAME `ChatbotSettings` draft/save the page's Switches card already owns (one
 * consolidated Save, 16 Sep 2026 browser pass) - this card owns no query, no mutation,
 * no toast and renders no Save button of its own. The existing card layout in this
 * folder (`MemorySettingsCard`, `TierOrderCard`) is reused as-is; no new motion.
 */
export default function StockLowThresholdCard({
  value,
  onChange,
}: {
  value: number | null;
  onChange: (value: number) => void;
}) {
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const raw = event.target.value;
    if (raw === '') return;
    const parsed = Number(raw);
    if (Number.isNaN(parsed)) return;
    onChange(Math.min(100, Math.max(1, parsed)));
  };

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Stock low threshold</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1.5 py-5">
        {/* Visible copy stays "Threshold (%)" - the card title already says "Stock low
            threshold", so a label repeating the full phrase would duplicate it on screen.
            The input's accessible name is the full "Stock low threshold (%)" via
            `aria-label` (it wins over the associated `<label>` for name computation),
            which is what a screen reader and the test's role query both read. */}
        <Label htmlFor="chatbot-stock-low-threshold-pct">Threshold (%)</Label>
        <Input
          id="chatbot-stock-low-threshold-pct"
          aria-label="Stock low threshold (%)"
          type="number"
          min={1}
          max={100}
          value={value ?? ''}
          onChange={handleChange}
          className="max-w-32"
        />
      </CardContent>
    </Card>
  );
}
