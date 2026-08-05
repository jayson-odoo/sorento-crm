'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { getProductSpecDetail } from '../../../product-specifications/services/productSpecService';
import type {
  ProductSpecDetail,
  SpecDiagnosisReason,
} from '../../../product-specifications/types/productSpec.types';

/**
 * What the machine read out of THIS product, and what search will do with it.
 *
 * Opened while looking at one product, so it answers the question asked there: can a
 * customer find this by describing it, and if not, what is stopping it. Every value
 * carries the exact substring it came from, because the only way to trust a derived
 * spec is to see the words it was derived from sitting next to it.
 */

const EXCEPTION_LABELS: Record<string, string> = {
  shape_mismatch: 'Stored dimensions describe a round or square product',
  column_conflict: 'Description disagrees with the stored dimensions',
  implausible_dimension: 'Dimension too large to be real',
  low_confidence: 'Derived below the review threshold',
};

/** Each silence gets its own sentence and its own fix. */
function diagnosisCopy(
  detail: ProductSpecDetail,
): { title: string; body: string; tone: 'warning' | 'destructive' } {
  const reason: SpecDiagnosisReason = detail.diagnosis.reason;
  const suffix = detail.diagnosis.suffix;

  switch (reason) {
    case 'class_not_enabled':
      return {
        tone: 'warning',
        title: `Product class "${suffix}" is not switched on yet`,
        body:
          `This product sits in category ${detail.category_code}. Spec derivation currently ` +
          'runs for Kitchen Sink only — the pilot class. Nothing about this product has ' +
          'been read, so a customer describing it will not find it. Widening the class ' +
          'list is what turns this on.',
      };
    case 'category_non_searchable':
      return {
        tone: 'warning',
        title: `Category ${detail.category_code} carries no product class`,
        body:
          'Codes like MISC, PROJECT, SRTPART and VD are deliberately marked ' +
          'non-searchable: they say nothing about what the product is, so guessing a ' +
          'class from them would hand the ranker its most damaging possible value.',
      };
    case 'code_unparsed':
      return {
        tone: 'destructive',
        title: `Category code ${detail.category_code} does not decompose`,
        body:
          'Codes are read as BRAND-CLASS. This one has no class half, so neither signal ' +
          'could be recovered. It needs either a corrected code or an explicit mapping.',
      };
    case 'no_category':
      return {
        tone: 'destructive',
        title: 'This product has no category',
        body:
          'Class is the single largest ranking signal and it comes from the category ' +
          'code. Without a category there is nothing to derive from.',
      };
    case 'not_yet_derived':
    default:
      return {
        tone: 'warning',
        title: 'Eligible, but nothing derived yet',
        body:
          `Class "${detail.diagnosis.class_label}" is switched on, so this product should ` +
          'have specs. The derivation job has not covered it — re-running derivation for ' +
          'this class will populate it.',
      };
  }
}

export default function ProductSpecificationsTab({ productId }: { productId: string }) {
  const [detail, setDetail] = useState<ProductSpecDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getProductSpecDetail(productId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [productId]);

  if (loading) {
    return (
      <Card>
        <CardContent className="flex flex-col gap-2 pt-6">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertIcon />
        <AlertTitle>{error}</AlertTitle>
      </Alert>
    );
  }

  if (!detail) return null;

  const values = detail.spec?.values ?? {};
  const provenance = detail.spec?.provenance ?? {};
  const entries = Object.entries(values).sort(([a], [b]) => a.localeCompare(b));
  const copy = detail.searchable ? null : diagnosisCopy(detail);

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>Derived specifications</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            {detail.searchable ? (
              <Badge variant="success" size="sm">
                Findable by description
              </Badge>
            ) : (
              <Badge variant="secondary" size="sm">
                Not findable by description
              </Badge>
            )}
            {detail.spec?.status && (
              <Badge variant="outline" size="sm">
                {detail.spec.status.replace(/_/g, ' ')}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          {copy && (
            <Alert variant={copy.tone}>
              <AlertIcon />
              <div className="flex flex-col gap-1">
                <AlertTitle>{copy.title}</AlertTitle>
                <p className="text-sm">{copy.body}</p>
              </div>
            </Alert>
          )}

          <div className="flex flex-col gap-1.5">
            <div className="text-xs uppercase tracking-wide text-muted-foreground">
              Text the derivation read
            </div>
            <p className="rounded-md border bg-muted/30 p-3 font-mono text-sm break-words">
              {detail.source_text || '(no description)'}
            </p>
          </div>

          {detail.spec?.rendered_text && (
            <div className="flex flex-col gap-1.5">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                What search actually matches
              </div>
              <p className="rounded-md border p-3 text-sm break-words">
                {detail.spec.rendered_text}
              </p>
              <p className="text-xs text-muted-foreground">
                Product codes are stripped on purpose — a description that names another
                product&apos;s code must never make this row match that code.
              </p>
            </div>
          )}

          {entries.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                Every value, and the text it was read from
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                      <th className="pb-2 pr-4">Spec</th>
                      <th className="pb-2 pr-4">Value</th>
                      <th className="pb-2 pr-4">Read from</th>
                      <th className="pb-2">How</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entries.map(([key, value]) => (
                      <tr key={key} className="border-b last:border-0">
                        <td className="py-2 pr-4 whitespace-nowrap">
                          {key.replace(/_/g, ' ')}
                        </td>
                        <td className="py-2 pr-4 font-mono whitespace-nowrap">
                          {String(value.value)}
                          {value.unit ? ` ${value.unit}` : ''}
                        </td>
                        <td className="py-2 pr-4 font-mono text-xs text-muted-foreground break-all">
                          {provenance[key]?.evidence ?? '-'}
                        </td>
                        <td className="py-2 text-xs text-muted-foreground whitespace-nowrap">
                          {provenance[key]?.source ?? '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {detail.exceptions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Needs a human ({detail.exceptions.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="pb-2 pr-4">Spec</th>
                    <th className="pb-2 pr-4">Why</th>
                    <th className="pb-2">Stored</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.exceptions.map((row) => (
                    <tr key={row.id} className="border-b last:border-0">
                      <td className="py-2 pr-4">{row.spec_key}</td>
                      <td className="py-2 pr-4">
                        {EXCEPTION_LABELS[row.reason] ?? row.reason}
                      </td>
                      <td className="py-2 font-mono text-xs text-muted-foreground">
                        {row.stored ? JSON.stringify(row.stored) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      <p className="text-sm text-muted-foreground">
        To try a customer phrase against the whole catalog, use{' '}
        <Link
          href="/master-data-management/product-specifications"
          className="underline underline-offset-2"
        >
          Product Specifications
        </Link>
        .
      </p>
    </div>
  );
}
