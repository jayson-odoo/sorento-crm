'use client';

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LoaderCircleIcon } from 'lucide-react';
import { RiErrorWarningFill } from '@remixicon/react';
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
import { Skeleton } from '@/components/ui/skeleton';
import { getCompaniesSelect } from '@/app/(protected)/system-management/companies/services/companyService';
import { useSettings } from '../components/settings-context';

/** Sorento. Matches app.services.company_scope.DEFAULT_COMPANY_ID. */
const DEFAULT_COMPANY_ID = '00000000-0000-0000-0000-000000000001';

function parseIds(raw: string | null | undefined): string[] {
  return (raw ?? '')
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean);
}

/**
 * Which companies the discontinued-product check reports on.
 *
 * The job reads `products` with the scheduler's company scope set to all companies,
 * so it is company-blind by nature. Left alone, the day a second company's catalogue
 * is loaded its entire discontinued history arrives in one notification aimed at
 * staff who do not handle it. Opting a company IN is the deliberate act.
 *
 * Before enabling a company for the first time, run
 * `scripts/stamp_discontinued_backlog.py --company <code> --apply` or the first tick
 * reports that company's whole history as though it just happened.
 */
export default function DiscontinuedNotifyCompaniesCard({
  toast,
}: {
  toast: (variant: 'success' | 'destructive', message: string) => void;
}) {
  const queryClient = useQueryClient();
  const { settings } = useSettings();

  const { data: companies, isLoading } = useQuery({
    queryKey: ['companies-select'],
    queryFn: getCompaniesSelect,
  });

  // Blank means "Sorento only" - resolved in the backend, mirrored here so the
  // checkboxes show what will actually happen rather than an empty selection.
  const initial = useMemo(() => {
    const ids = parseIds(settings.productDiscontinuedNotifyCompanyIds);
    return ids.length > 0 ? ids : [DEFAULT_COMPANY_ID];
  }, [settings.productDiscontinuedNotifyCompanyIds]);

  const [selected, setSelected] = useState<string[]>(initial);
  useEffect(() => setSelected(initial), [initial]);

  const toggle = (id: string) =>
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );

  const mutation = useMutation({
    mutationFn: async (ids: string[]) => {
      // apiFetch maps /api/... straight to the FastAPI backend; POST /general
      // setattrs any provided snake_case column.
      const response = await apiFetch('/api/user-management/settings/general', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_discontinued_notify_company_ids: ids.join(',') }),
      });
      if (!response.ok) {
        const { message } = await response
          .json()
          .catch(() => ({ message: 'Failed to save' }));
        throw new Error(message || 'Failed to save');
      }
      return response.json();
    },
    onSuccess: () => {
      toast('success', 'Discontinued-product notification companies updated');
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
    },
    onError: (error: Error) => toast('destructive', error.message),
  });

  const isProcessing = mutation.status === 'pending';

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>Discontinued products - companies to report on</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5 py-5">
        <div className="text-muted-foreground text-2sm">
          The discontinued-product check reports each selected company separately, so
          a count and its link always belong to one catalogue. Before switching a
          company on for the first time, stamp its existing discontinued products or
          the first run reports that company&apos;s entire history at once.
        </div>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-5 w-40" />
          </div>
        ) : (companies ?? []).length === 0 ? (
          <div className="text-muted-foreground text-2sm">No companies found.</div>
        ) : (
          <div className="space-y-3">
            {(companies ?? []).map((c) => (
              <label
                key={c.id}
                className="flex items-center gap-3 cursor-pointer"
                htmlFor={`disc-co-${c.id}`}
              >
                <Checkbox
                  id={`disc-co-${c.id}`}
                  checked={selected.includes(c.id)}
                  onCheckedChange={() => toggle(c.id)}
                />
                <span className="text-sm">
                  {c.name} <span className="text-muted-foreground">({c.code})</span>
                </span>
              </label>
            ))}
          </div>
        )}
        {selected.length === 0 && (
          <Alert variant="mono" icon="warning">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertTitle>
              No company selected - saving this reverts to Sorento only.
            </AlertTitle>
          </Alert>
        )}
      </CardContent>
      <CardFooter className="flex justify-end gap-4 py-5 px-10">
        <Button type="button" variant="outline" onClick={() => setSelected(initial)}>
          Reset
        </Button>
        <Button
          type="button"
          onClick={() => mutation.mutate(selected)}
          disabled={isProcessing}
        >
          {isProcessing && <LoaderCircleIcon className="animate-spin" />}
          Save Settings
        </Button>
      </CardFooter>
    </Card>
  );
}
