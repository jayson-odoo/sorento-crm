'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { AlertCircle, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';

interface ViewLineSummary {
  item_code?: string | null;
  quantity?: number | null;
  remark?: string | null;
  sort_order?: number | null;
}

interface ViewSummary {
  entity_type: string;
  entity_id: string;
  request_number: string | null;
  request_type: string;
  customer_name: string | null;
  project_title: string | null;
  purpose: string | null;
  requested_by: string | null;
  request_date: string | null;
  created_at: string | null;
  expected_delivery_date: string | null;
  expected_po_date: string | null;
  expected_po_date_text: string | null;
  expires_at?: string | null;
  lines?: ViewLineSummary[] | null;
}

const REQUEST_TYPE_LABELS: Record<string, string> = {
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
};

function formatDateStr(value: string | null | undefined): string {
  if (!value) return '—';
  try {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, { dateStyle: 'medium' });
  } catch {
    return value;
  }
}

function formatDateTimeStr(value: string | null | undefined): string {
  if (!value) return '—';
  try {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? value : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return value;
  }
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === '' || (typeof value === 'string' && value.trim() === '')) return null;
  return (
    <div className="py-2.5 border-b border-border/60 last:border-0">
      <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">{label}</p>
      <p className="text-sm font-medium break-words">{value}</p>
    </div>
  );
}

function ViewRequestContent() {
  const searchParams = useSearchParams();
  const token = searchParams?.get('token') ?? '';
  const [summary, setSummary] = useState<ViewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    if (!token) {
      setError('Invalid or missing view link.');
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`/api/v1/public/view/request?token=${encodeURIComponent(token)}`);
      const data = await res.json();
      if (res.ok) {
        setSummary(data);
        setError(null);
      } else {
        const msg =
          (typeof data.detail === 'object' && data.detail && 'message' in data.detail
            ? (data.detail as { message?: string }).message
            : null) ||
          (typeof data.detail === 'string' ? data.detail : null) ||
          data.message ||
          'This link is invalid.';
        setError(msg);
      }
    } catch {
      setError('Failed to load details.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  if (loading) {
    return (
      <div className="min-h-screen max-w-lg mx-auto px-4 py-6 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (error && !summary) {
    return (
      <div className="min-h-screen max-w-lg mx-auto px-4 py-6 space-y-6">
        <h1 className="text-xl sm:text-2xl font-semibold">View Request</h1>
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      </div>
    );
  }

  const typeLabel = REQUEST_TYPE_LABELS[summary?.request_type ?? ''] ?? summary?.request_type ?? 'Request';
  const poDisplay = summary?.expected_po_date_text?.trim() || (summary?.expected_po_date ? formatDateStr(summary.expected_po_date) : null);

  const viewInSystemPath =
    summary?.entity_id && summary?.request_type
      ? summary.request_type === 'sponsorship_form'
        ? `/procurement-management/sponsorship-forms/${summary.entity_id}`
        : `/procurement-management/purchase-requests/${summary.entity_id}`
      : null;

  return (
    <div className="min-h-screen max-w-lg mx-auto px-4 py-6 space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl sm:text-2xl font-semibold leading-tight">{typeLabel}</h1>
        {viewInSystemPath && (
          <Button variant="outline" size="sm" className="shrink-0" asChild>
            <Link href={viewInSystemPath}>
              <ExternalLink className="h-4 w-4 mr-2" />
              View in system
            </Link>
          </Button>
        )}
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      )}
      <Card className="overflow-hidden">
        <CardHeader className="pb-2">
          <CardTitle className="text-base sm:text-lg">
            {summary?.request_number ? `Form #${summary.request_number}` : 'Details'}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 sm:px-6 -mt-2 space-y-0">
          <DetailRow label="Type" value={typeLabel} />
          <DetailRow label="Form number" value={summary?.request_number ?? undefined} />
          <DetailRow label="Customer" value={summary?.customer_name ?? undefined} />
          <DetailRow label="Project" value={summary?.project_title ?? undefined} />
          <DetailRow label="Purpose" value={summary?.purpose ?? undefined} />
          <DetailRow label="Requested by" value={summary?.requested_by ?? undefined} />
          <DetailRow label="Request date" value={summary?.request_date ? formatDateStr(summary.request_date) : undefined} />
          <DetailRow label="Created at" value={summary?.created_at ? formatDateTimeStr(summary.created_at) : undefined} />
          <DetailRow label="Expected delivery" value={summary?.expected_delivery_date ? formatDateStr(summary.expected_delivery_date) : undefined} />
          <DetailRow label="Expected PO date" value={poDisplay ?? undefined} />
          {summary?.lines && summary.lines.length > 0 && (
            <div className="pt-4 mt-2 border-t border-border">
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-3">Line items</p>
              <div className="space-y-3">
                {summary.lines.map((line, idx) => (
                  <div
                    key={idx}
                    className="rounded-md border border-border/60 bg-muted/30 p-3 space-y-1.5"
                  >
                    <p className="text-xs text-muted-foreground uppercase tracking-wide">Product</p>
                    <p className="text-sm font-medium break-words">{line.item_code ?? '—'}</p>
                    <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1.5">Quantity</p>
                    <p className="text-sm font-medium">{line.quantity != null ? String(line.quantity) : '—'}</p>
                    {(line.remark != null && String(line.remark).trim() !== '') && (
                      <>
                        <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1.5">Remarks</p>
                        <p className="text-sm font-medium break-words">{line.remark}</p>
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function ViewRequestPage() {
  return (
    <Suspense fallback={<Skeleton className="h-32 w-full" />}>
      <ViewRequestContent />
    </Suspense>
  );
}
