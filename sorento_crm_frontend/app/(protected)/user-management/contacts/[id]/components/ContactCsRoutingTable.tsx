'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { extractApiError } from '@/lib/api-client';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * Per-salesman → CS PIC pin-point routing for procurement form-SLA CS handoff.
 *
 * Each procurement use_case (Purchase Request, Sponsorship Form) can be pinned to a
 * specific customer-service PIC, overriding the default round-robin at approval. The
 * candidate list is the tier-1 members of the customer-service team (purchase_request
 * agent). Leaving a row as "Round-robin (default)" clears the pin.
 *
 * See docs/plans/PLAN-procurement-cs-handoff-and-pinpoint-routing.md.
 */

const ROUND_ROBIN = '__round_robin__';

const USE_CASES: { key: string; label: string }[] = [
  { key: 'purchase_request', label: 'Purchase Request' },
  { key: 'sponsorship_form', label: 'Sponsorship Form' },
];

interface Candidate {
  id: string;
  name: string;
  email: string;
}

interface Pin {
  use_case: string;
  cs_pic_user_id: string;
  cs_pic_name: string | null;
}

export default function ContactCsRoutingTable({ contactId }: { contactId: string }) {
  const queryClient = useQueryClient();

  const { data: candidates = [], isLoading: candidatesLoading } = useQuery({
    queryKey: ['cs-routing-candidates'],
    queryFn: async () => {
      const res = await apiFetch('/api/v1/user-management/contacts/cs-routing/candidates');
      if (!res.ok) throw new Error('Failed to load CS team');
      const data = (await res.json()) as { candidates: Candidate[] };
      return data.candidates ?? [];
    },
    staleTime: 60_000,
  });

  const {
    data: pins = [],
    isLoading: pinsLoading,
  } = useQuery({
    queryKey: ['cs-routing', contactId],
    queryFn: async () => {
      const res = await apiFetch(
        `/api/v1/user-management/contacts/${contactId}/cs-routing`,
      );
      if (!res.ok) throw new Error('Failed to load CS routing');
      const data = (await res.json()) as { pins: Pin[] };
      return data.pins ?? [];
    },
    enabled: !!contactId,
  });

  const saveMutation = useMutation({
    mutationFn: async ({ useCase, userId }: { useCase: string; userId: string }) => {
      if (userId === ROUND_ROBIN) {
        const res = await apiFetch(
          `/api/v1/user-management/contacts/${contactId}/cs-routing/${useCase}`,
          { method: 'DELETE' },
        );
        if (!res.ok && res.status !== 204) throw new Error('Failed to clear pin');
        return;
      }
      const res = await apiFetch(
        `/api/v1/user-management/contacts/${contactId}/cs-routing/${useCase}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cs_pic_user_id: userId }),
        },
      );
      if (!res.ok) {
        throw new Error(await extractApiError(res, 'Failed to save pin'));
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cs-routing', contactId] });
      toast.success('CS assignment updated');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update CS assignment'),
  });

  const pinFor = (useCase: string) =>
    pins.find((p) => p.use_case === useCase)?.cs_pic_user_id ?? ROUND_ROBIN;

  if (candidatesLoading || pinsLoading) {
    return (
      <div className="px-6 pb-6 space-y-3">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  return (
    <div className="px-6 pb-6 space-y-4">
      <p className="text-sm text-muted-foreground">
        Pin this salesman to a specific customer-service PIC for each form type. The
        pinned PIC is assigned automatically when the form is approved; leave as
        round-robin to use the default rotation.
      </p>
      {candidates.length === 0 ? (
        <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          No customer-service team configured yet. Add members to the customer-service
          team (Purchase Request agent, tier 1) before pinning.
        </div>
      ) : (
        <div className="space-y-3">
          {USE_CASES.map((uc) => (
            <div
              key={uc.key}
              className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4"
            >
              <p className="text-sm font-medium w-full sm:w-48 shrink-0">{uc.label}</p>
              <Select
                value={pinFor(uc.key)}
                onValueChange={(userId) =>
                  saveMutation.mutate({ useCase: uc.key, userId })
                }
                disabled={saveMutation.isPending}
              >
                <SelectTrigger className="w-full sm:max-w-sm">
                  <SelectValue placeholder="Round-robin (default)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ROUND_ROBIN}>Round-robin (default)</SelectItem>
                  {candidates.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
