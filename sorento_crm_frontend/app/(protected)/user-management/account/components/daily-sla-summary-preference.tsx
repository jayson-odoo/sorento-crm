'use client';

import { useEffect, useState } from 'react';
import { toast } from '@/lib/toast';
import { apiFetch } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

export default function DailySLASummaryPreference() {
  const [subscribed, setSubscribed] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const run = async () => {
      try {
        const res = await apiFetch('/api/v1/notifications/preferences/daily-sla-summary');
        if (!res.ok) throw new Error('Failed to load preference');
        const data = (await res.json()) as { subscribed?: boolean };
        setSubscribed(Boolean(data.subscribed));
      } catch {
        // Keep default to avoid blocking page.
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, []);

  const onToggle = async (next: boolean) => {
    setSubscribed(next);
    try {
      const res = await apiFetch(
        `/api/v1/notifications/preferences/daily-sla-summary?subscribed=${next ? 'true' : 'false'}`,
        { method: 'PATCH' },
      );
      if (!res.ok) throw new Error('Failed to save preference');
      toast.success(
        next
          ? 'Conversation summary subscribed'
          : 'Conversation summary unsubscribed',
      );
    } catch {
      setSubscribed(!next);
      toast.error('Unable to update subscription');
    }
  };

  return (
    <Card>
      <CardHeader className="py-4">
        <CardTitle>Conversation Summary</CardTitle>
      </CardHeader>
      <CardContent className="py-4">
        <div className="flex items-center justify-between">
          <Label htmlFor="daily-sla-summary-subscription">
            Daily conversation SLA summary
          </Label>
          <Switch
            id="daily-sla-summary-subscription"
            checked={subscribed}
            disabled={loading}
            onCheckedChange={onToggle}
          />
        </div>
      </CardContent>
    </Card>
  );
}
