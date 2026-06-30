'use client';

import { useMemo, useState } from 'react';
import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { LoaderCircleIcon } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { useSettings } from '../components/settings-context';

const TIERS = [1, 2, 3] as const;

/** Parse a comma list ("1,2") into a set of valid tier numbers. */
function parseTiers(raw: string | null | undefined): Set<number> {
  const out = new Set<number>();
  (raw ?? '')
    .split(',')
    .map((p) => parseInt(p.trim(), 10))
    .forEach((n) => {
      if (n >= 1 && n <= 3) out.add(n);
    });
  return out;
}

const ComplaintSettingsPage = () => {
  const queryClient = useQueryClient();
  const { settings } = useSettings();

  const initial = useMemo(
    () => parseTiers(settings.complaintDoDeliveredNotifyTiers),
    [settings.complaintDoDeliveredNotifyTiers],
  );
  const [selected, setSelected] = useState<Set<number>>(new Set(initial));

  const toggle = (tier: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(tier)) next.delete(tier);
      else next.add(tier);
      return next;
    });
  };

  const mutation = useMutation({
    mutationFn: async (tiers: string) => {
      // apiFetch maps /api/... straight to the FastAPI backend; POST /general
      // setattrs any provided column (here the snake_case tiers string).
      const response = await apiFetch('/api/user-management/settings/general', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ complaint_do_delivered_notify_tiers: tiers }),
      });
      if (!response.ok) {
        const { message } = await response.json().catch(() => ({ message: 'Failed to save' }));
        throw new Error(message || 'Failed to save');
      }
      return response.json();
    },
    onSuccess: () => {
      toast('success', 'Complaint settings updated');
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
    },
    onError: (error: Error) => toast('destructive', error.message),
  });

  const isProcessing = mutation.status === 'pending';

  const handleSave = () => {
    const tiers = TIERS.filter((t) => selected.has(t)).join(',');
    mutation.mutate(tiers);
  };

  const handleReset = () => setSelected(new Set(initial));

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Complaint Settings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5 py-5">
        <div className="space-y-1">
          <div className="text-md font-semibold">
            Replacement DO delivered — notify team tiers
          </div>
          <div className="text-muted-foreground text-2sm">
            When a replacement delivery order for a complaint is delivered, email
            and notify these tiers of the Complaint team. Membership is managed in{' '}
            User Management → Teams.
          </div>
        </div>
        <div className="space-y-3">
          {TIERS.map((tier) => (
            <label
              key={tier}
              className="flex items-center gap-3 cursor-pointer"
              htmlFor={`tier-${tier}`}
            >
              <Checkbox
                id={`tier-${tier}`}
                checked={selected.has(tier)}
                onCheckedChange={() => toggle(tier)}
              />
              <span className="text-sm">Tier {tier}</span>
            </label>
          ))}
        </div>
        {selected.size === 0 && (
          <Alert variant="mono" icon="warning">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertTitle>
              No tier selected — no one will be notified when a replacement DO is
              delivered.
            </AlertTitle>
          </Alert>
        )}
      </CardContent>
      <CardFooter className="flex justify-end gap-4 py-5 px-10">
        <Button type="button" variant="outline" onClick={handleReset}>
          Reset
        </Button>
        <Button type="button" onClick={handleSave} disabled={isProcessing}>
          {isProcessing && <LoaderCircleIcon className="animate-spin" />}
          Save Settings
        </Button>
      </CardFooter>
    </Card>
  );
};

function toast(icon: 'success' | 'destructive', title: string) {
  // Lazy import to keep parity with the rest of the settings pages.
  import('sonner').then(({ toast: sonner }) =>
    sonner.custom(
      () => (
        <Alert variant="mono" icon={icon}>
          <AlertIcon>
            {icon === 'success' ? <RiCheckboxCircleFill /> : <RiErrorWarningFill />}
          </AlertIcon>
          <AlertTitle>{title}</AlertTitle>
        </Alert>
      ),
      { position: 'top-center' },
    ),
  );
}

export default ComplaintSettingsPage;
