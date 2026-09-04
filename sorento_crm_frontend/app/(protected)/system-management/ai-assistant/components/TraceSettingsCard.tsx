'use client';

import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { toast } from '@/lib/toast';

interface TraceSettings {
  ai_assistant_role_split_enabled: boolean;
  ai_trace_ttl_days: number;
  ai_trace_error_ttl_days: number;
  ai_trace_max_payload_bytes: number;
}

const DEFAULTS: TraceSettings = {
  ai_assistant_role_split_enabled: false,
  ai_trace_ttl_days: 30,
  ai_trace_error_ttl_days: 90,
  ai_trace_max_payload_bytes: 16384,
};

/**
 * Admin controls for the per-turn trace (M2) + role-split pipeline (M2.5).
 * Reads/writes the `system_settings` singleton via the general-settings API
 * (apiFetch maps `/api/user-management/...` straight to the FastAPI backend).
 */
export default function TraceSettingsCard() {
  const [form, setForm] = useState<TraceSettings>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await apiFetch('/api/user-management/settings/');
        if (!res.ok) {
          if (alive) setLoadFailed(true);
          return;
        }
        const data = await res.json();
        const s = data?.settings ?? {};
        if (!alive) return;
        setForm({
          ai_assistant_role_split_enabled: !!s.ai_assistant_role_split_enabled,
          ai_trace_ttl_days: Number(s.ai_trace_ttl_days ?? DEFAULTS.ai_trace_ttl_days),
          ai_trace_error_ttl_days: Number(s.ai_trace_error_ttl_days ?? DEFAULTS.ai_trace_error_ttl_days),
          ai_trace_max_payload_bytes: Number(
            s.ai_trace_max_payload_bytes ?? DEFAULTS.ai_trace_max_payload_bytes,
          ),
        });
      } catch {
        if (alive) setLoadFailed(true);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const mutation = useMutation({
    mutationFn: async (payload: TraceSettings) => {
      const res = await apiFetch('/api/user-management/settings/general', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const { message } = await res.json().catch(() => ({ message: 'Failed to save' }));
        throw new Error(message || 'Failed to save');
      }
      return res.json();
    },
    onSuccess: () => toast.success('Tracing settings saved'),
    onError: (e: Error) => toast.error(e.message),
  });

  const num = (v: string, fallback: number) => {
    const n = parseInt(v, 10);
    return Number.isFinite(n) ? n : fallback;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Tracing &amp; diagnostics</CardTitle>
        <CardDescription>
          Per-turn pipeline traces (waterfall of every node) and the experimental role-split
          executor. Traces are admin-only and auto-swept by retention.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {loading ? (
          <SectionSkeleton rows={3} />
        ) : loadFailed ? (
          <div data-testid="trace-settings-load-failed" className="text-sm text-destructive">
            Could not load the current tracing settings, so they cannot be edited here. This
            usually means the account lacks permission to read system settings.
          </div>
        ) : (
          <>
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-0.5">
                <Label htmlFor="role-split">Role-split executor (M2.5)</Label>
                <p className="text-xs text-muted-foreground">
                  Run an explicit planner node and compress raw tool JSON via the
                  semantic-compressor before the executor sees it. Adds LLM calls; leave off unless
                  debugging or benchmarking.
                </p>
              </div>
              <Switch
                id="role-split"
                data-testid="role-split-toggle"
                checked={form.ai_assistant_role_split_enabled}
                onCheckedChange={(v) =>
                  setForm((f) => ({ ...f, ai_assistant_role_split_enabled: v }))
                }
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-1">
                <Label htmlFor="ttl">Trace retention (days)</Label>
                <Input
                  id="ttl"
                  type="number"
                  min={1}
                  value={form.ai_trace_ttl_days}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, ai_trace_ttl_days: num(e.target.value, 30) }))
                  }
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="err-ttl">Error/flagged retention (days)</Label>
                <Input
                  id="err-ttl"
                  type="number"
                  min={1}
                  value={form.ai_trace_error_ttl_days}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, ai_trace_error_ttl_days: num(e.target.value, 90) }))
                  }
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="cap">Payload cap (bytes)</Label>
                <Input
                  id="cap"
                  type="number"
                  min={512}
                  value={form.ai_trace_max_payload_bytes}
                  onChange={(e) =>
                    setForm((f) => ({
                      ...f,
                      ai_trace_max_payload_bytes: num(e.target.value, 16384),
                    }))
                  }
                />
              </div>
            </div>

            <div className="flex justify-end">
              <Button
                type="button"
                onClick={() => mutation.mutate(form)}
                disabled={mutation.status === 'pending'}
              >
                {mutation.status === 'pending' ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  'Save'
                )}
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
