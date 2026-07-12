'use client';

import { useMemo, useState } from 'react';
import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { LoaderCircleIcon } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
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
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { useSettings } from '../components/settings-context';

const TIERS = [1, 2, 3] as const;

// Per-form handling-lock ("I'm handling this") feature flag — one toggle per form type.
const HANDLING_LOCK_FORMS = [
  { type: 'complaint', label: 'Complaint' },
  { type: 'stock_inquiry', label: 'Stock Inquiry' },
  { type: 'purchase_request', label: 'Purchase Request' },
  { type: 'sponsorship_form', label: 'Sponsorship Form' },
] as const;

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
    <div className="space-y-5">
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
    <HandlingLockSettingsCard />
    </div>
  );
};

/**
 * Per-form handling-lock feature flag (PLAN-form-handling-lock, P2-15 / F-5). When on for a
 * form type, an escalated form of that type locks its state-changing CTAs until an eligible
 * team-chain member claims it via "I'm handling this". Off = today's behaviour (no lock).
 * Persists to system_settings.handling_lock_enabled_types (a list of source_entity_types).
 */
const HandlingLockSettingsCard = () => {
  const queryClient = useQueryClient();
  const { settings } = useSettings();

  const initial = useMemo(
    () => new Set(settings.handlingLockEnabledTypes ?? []),
    [settings.handlingLockEnabledTypes],
  );
  const [enabled, setEnabled] = useState<Set<string>>(new Set(initial));

  const dirty = useMemo(() => {
    if (enabled.size !== initial.size) return true;
    for (const t of enabled) if (!initial.has(t)) return true;
    return false;
  }, [enabled, initial]);

  const mutation = useMutation({
    mutationFn: async (types: string[]) => {
      // apiFetch maps /api/... straight to the backend; POST /general accepts a list and
      // normalizes it to a de-duped CSV of valid form types.
      const response = await apiFetch('/api/user-management/settings/general', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ handling_lock_enabled_types: types }),
      });
      if (!response.ok) {
        throw new Error(await extractApiError(response, 'Failed to save'));
      }
      return response.json();
    },
    onSuccess: () => {
      toast('success', 'Handling-lock settings updated');
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
    },
    onError: (error: Error) => toast('destructive', error.message),
  });

  const isProcessing = mutation.status === 'pending';

  const toggle = (type: string, next: boolean) => {
    setEnabled((prev) => {
      const out = new Set(prev);
      if (next) out.add(type);
      else out.delete(type);
      return out;
    });
  };

  const handleSave = () =>
    mutation.mutate(HANDLING_LOCK_FORMS.filter((f) => enabled.has(f.type)).map((f) => f.type));

  const handleReset = () => setEnabled(new Set(initial));

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Form Handling Lock</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5 py-5">
        <div className="space-y-1">
          <div className="text-md font-semibold">Enable “I’m handling this” per form</div>
          <div className="text-muted-foreground text-2sm">
            When enabled, an escalated form of this type locks its action buttons until an
            eligible team member claims it. Turn off to keep today’s behaviour.
          </div>
        </div>
        <div className="space-y-4">
          {HANDLING_LOCK_FORMS.map((form) => (
            <div key={form.type} className="flex items-center justify-between">
              <Label htmlFor={`handling-lock-${form.type}`}>{form.label}</Label>
              <Switch
                id={`handling-lock-${form.type}`}
                checked={enabled.has(form.type)}
                onCheckedChange={(v) => toggle(form.type, v)}
              />
            </div>
          ))}
        </div>
      </CardContent>
      <CardFooter className="flex justify-end gap-4 py-5 px-10">
        <Button type="button" variant="outline" onClick={handleReset} disabled={!dirty}>
          Reset
        </Button>
        <Button type="button" onClick={handleSave} disabled={isProcessing || !dirty}>
          {isProcessing && <LoaderCircleIcon className="animate-spin" />}
          Save handling lock
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
