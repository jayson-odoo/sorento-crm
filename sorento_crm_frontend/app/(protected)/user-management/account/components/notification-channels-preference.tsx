'use client';

import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

type ChannelPrefs = {
  notify_whatsapp_summary: boolean;
  notify_email_on_assignment: boolean;
  notify_email_on_escalation: boolean;
  notify_whatsapp_on_assignment: boolean;
  notify_whatsapp_on_escalation: boolean;
  notify_email_on_deadline_extended: boolean;
  notify_whatsapp_on_deadline_extended: boolean;
  notify_email_on_handling: boolean;
  notify_whatsapp_on_handling: boolean;
  notify_email_on_mention: boolean;
};

const SLA_TOGGLES: { key: keyof ChannelPrefs; label: string }[] = [
  { key: 'notify_email_on_assignment', label: 'Email on assignment' },
  { key: 'notify_email_on_escalation', label: 'Email on escalation' },
  { key: 'notify_whatsapp_on_assignment', label: 'WhatsApp on assignment' },
  { key: 'notify_whatsapp_on_escalation', label: 'WhatsApp on escalation' },
  { key: 'notify_email_on_deadline_extended', label: 'Email on deadline extended' },
  { key: 'notify_whatsapp_on_deadline_extended', label: 'WhatsApp on deadline extended' },
  { key: 'notify_email_on_handling', label: 'Email on handling (claimed / taken over / released)' },
  { key: 'notify_whatsapp_on_handling', label: 'WhatsApp on handling (claimed / taken over / released)' },
  { key: 'notify_email_on_mention', label: 'Email on mention in a note' },
];

/**
 * Self-service WhatsApp channel toggles (TCK-31). Reads/writes the per-user
 * channel matrix at /notifications/preferences/channels. Independent of the
 * email daily-summary toggle (which lives in DailySLASummaryPreference).
 */
export default function NotificationChannelsPreference() {
  const [prefs, setPrefs] = useState<ChannelPrefs>({
    notify_whatsapp_summary: false,
    notify_email_on_assignment: true,
    notify_email_on_escalation: true,
    notify_whatsapp_on_assignment: false,
    notify_whatsapp_on_escalation: false,
    notify_email_on_deadline_extended: true,
    notify_whatsapp_on_deadline_extended: false,
    notify_email_on_handling: true,
    notify_whatsapp_on_handling: false,
    notify_email_on_mention: true,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const run = async () => {
      try {
        const res = await apiFetch('/api/v1/notifications/preferences/channels');
        if (!res.ok) throw new Error('Failed to load preferences');
        const data = (await res.json()) as Partial<ChannelPrefs>;
        setPrefs({
          notify_whatsapp_summary: Boolean(data.notify_whatsapp_summary),
          notify_email_on_assignment: data.notify_email_on_assignment ?? true,
          notify_email_on_escalation: data.notify_email_on_escalation ?? true,
          notify_whatsapp_on_assignment: Boolean(data.notify_whatsapp_on_assignment),
          notify_whatsapp_on_escalation: Boolean(data.notify_whatsapp_on_escalation),
          notify_email_on_deadline_extended: data.notify_email_on_deadline_extended ?? true,
          notify_whatsapp_on_deadline_extended: Boolean(data.notify_whatsapp_on_deadline_extended),
          notify_email_on_handling: data.notify_email_on_handling ?? true,
          notify_whatsapp_on_handling: Boolean(data.notify_whatsapp_on_handling),
          notify_email_on_mention: data.notify_email_on_mention ?? true,
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
        <CardTitle>SLA Notifications</CardTitle>
      </CardHeader>
      <CardContent className="py-4 space-y-4">
        {SLA_TOGGLES.map((t) => (
          <div key={t.key} className="flex items-center justify-between">
            <Label htmlFor={t.key}>{t.label}</Label>
            <Switch
              id={t.key}
              checked={prefs[t.key]}
              disabled={loading}
              onCheckedChange={(v) => onToggle(t.key, v)}
            />
          </div>
        ))}
        <div className="flex items-center justify-between">
          <Label htmlFor="notify-whatsapp-summary">WhatsApp daily SLA summary</Label>
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
