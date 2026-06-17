'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

type ChannelPrefs = {
  notify_whatsapp: boolean;
  notify_whatsapp_summary: boolean;
};

/**
 * Self-service WhatsApp channel toggles (TCK-31). Reads/writes the per-user
 * channel matrix at /notifications/preferences/channels. Independent of the
 * email daily-summary toggle (which lives in DailySLASummaryPreference).
 */
export default function NotificationChannelsPreference() {
  const [prefs, setPrefs] = useState<ChannelPrefs>({
    notify_whatsapp: false,
    notify_whatsapp_summary: false,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const run = async () => {
      try {
        const res = await apiFetch('/api/v1/notifications/preferences/channels');
        if (!res.ok) throw new Error('Failed to load preferences');
        const data = (await res.json()) as Partial<ChannelPrefs>;
        setPrefs({
          notify_whatsapp: Boolean(data.notify_whatsapp),
          notify_whatsapp_summary: Boolean(data.notify_whatsapp_summary),
        });
      } catch {
        // keep defaults; don't block the page
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, []);

  const onToggle = async (key: keyof ChannelPrefs, next: boolean) => {
    const prev = prefs;
    setPrefs({ ...prefs, [key]: next });
    try {
      const res = await apiFetch('/api/v1/notifications/preferences/channels', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: next }),
      });
      if (!res.ok) throw new Error('Failed to save preference');
      toast.success('Notification preference updated');
    } catch {
      setPrefs(prev);
      toast.error('Unable to update preference');
    }
  };

  return (
    <Card>
      <CardHeader className="py-4">
        <CardTitle>WhatsApp Notifications</CardTitle>
      </CardHeader>
      <CardContent className="py-4 space-y-4">
        <div className="flex items-center justify-between">
          <Label htmlFor="notify-whatsapp">Escalation & assignment alerts</Label>
          <Switch
            id="notify-whatsapp"
            checked={prefs.notify_whatsapp}
            disabled={loading}
            onCheckedChange={(v) => onToggle('notify_whatsapp', v)}
          />
        </div>
        <div className="flex items-center justify-between">
          <Label htmlFor="notify-whatsapp-summary">Daily SLA summary</Label>
          <Switch
            id="notify-whatsapp-summary"
            checked={prefs.notify_whatsapp_summary}
            disabled={loading}
            onCheckedChange={(v) => onToggle('notify_whatsapp_summary', v)}
          />
        </div>
      </CardContent>
    </Card>
  );
}
