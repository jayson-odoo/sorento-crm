'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { AlertCircle, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';

interface StockInquiryViewSummary {
  entity_type: string;
  entity_id: string;
  salesperson?: string | null;
  product_code?: string | null;
  item_description?: string | null;
  project_customer?: string | null;
  project_name?: string | null;
  quantity?: string | null;
  delivery_date?: string | null;
  remark?: string | null;
  additional_remark?: string | null;
  purchasing_response?: string | null;
  status?: string | null;
  last_responded_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

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
      <p className="text-sm font-medium break-words whitespace-pre-wrap">{value}</p>
    </div>
  );
}

function ViewStockInquiryContent() {
  const searchParams = useSearchParams();
  const token = searchParams?.get('token') ?? '';
  const [summary, setSummary] = useState<StockInquiryViewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    if (!token) {
      setError('Invalid or missing view link.');
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`/api/v1/public/view/stock-inquiry?token=${encodeURIComponent(token)}`);
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
        <h1 className="text-xl sm:text-2xl font-semibold">View Stock Inquiry</h1>
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      </div>
    );
  }

  const viewInSystemPath = summary?.entity_id
    ? `/procurement-management/stock-inquiries/${summary.entity_id}`
    : null;

  return (
    <div className="min-h-screen max-w-lg mx-auto px-4 py-6 space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl sm:text-2xl font-semibold leading-tight">Stock Inquiry</h1>
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
            {summary?.product_code ? `Product: ${summary.product_code}` : 'Stock inquiry details'}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 sm:px-6 -mt-2 space-y-0">
          <DetailRow label="Salesperson" value={summary?.salesperson ?? undefined} />
          <DetailRow label="Product code" value={summary?.product_code ?? undefined} />
          <DetailRow label="Item description" value={summary?.item_description ?? undefined} />
          <DetailRow label="Project customer" value={summary?.project_customer ?? undefined} />
          <DetailRow label="Project name" value={summary?.project_name ?? undefined} />
          <DetailRow label="Quantity" value={summary?.quantity ?? undefined} />
          <DetailRow label="Delivery date" value={summary?.delivery_date ?? undefined} />
          <DetailRow label="Remark" value={summary?.remark ?? undefined} />
          <DetailRow label="Additional remark" value={summary?.additional_remark ?? undefined} />
          <DetailRow label="Purchasing response" value={summary?.purchasing_response ?? undefined} />
          <DetailRow label="Status" value={summary?.status ?? undefined} />
          <DetailRow label="Last responded at" value={summary?.last_responded_at ? formatDateTimeStr(summary.last_responded_at) : undefined} />
          <DetailRow label="Created at" value={summary?.created_at ? formatDateTimeStr(summary.created_at) : undefined} />
          <DetailRow label="Updated at" value={summary?.updated_at ? formatDateTimeStr(summary.updated_at) : undefined} />
        </CardContent>
      </Card>
    </div>
  );
}

export default function ViewStockInquiryPage() {
  return (
    <Suspense fallback={<Skeleton className="h-32 w-full" />}>
      <ViewStockInquiryContent />
    </Suspense>
  );
}
