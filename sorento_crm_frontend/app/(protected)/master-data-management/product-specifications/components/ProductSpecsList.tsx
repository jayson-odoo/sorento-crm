'use client';

import { Fragment, useEffect, useState } from 'react';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { getProductSpecs, getSpecExceptions } from '../services/productSpecService';
import type { ProductSpecRow, SpecException } from '../types/productSpec.types';

const REASON_LABELS: Record<string, string> = {
  shape_mismatch: 'Stored dimensions describe a round or square product',
  column_conflict: 'Description disagrees with the stored dimensions',
  implausible_dimension: 'Dimension too large to be real',
  low_confidence: 'Derived below the review threshold',
};

/**
 * What the machine read out of the catalog, and what it wants a human to look at.
 *
 * The exception list is deliberately short: it holds only genuine conflicts, never
 * routine successes. If it ever fills up with ordinary rows, the filter is wrong and
 * this becomes the data-entry programme the design exists to avoid.
 */
export default function ProductSpecsList() {
  const [rows, setRows] = useState<ProductSpecRow[]>([]);
  const [exceptions, setExceptions] = useState<SpecException[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (search: string) => {
    setLoading(true);
    setError(null);
    try {
      const [specs, exc] = await Promise.all([
        getProductSpecs({ query: search, limit: 25 }),
        getSpecExceptions({ limit: 25 }),
      ]);
      setRows(specs.data);
      setTotal(specs.pagination.total);
      setExceptions(exc.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load specifications');
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load('');
  }, []);

  return (
    <div className="flex flex-col gap-5">
      {exceptions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Needs a human ({exceptions.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="pb-2 pr-4">Product</th>
                    <th className="pb-2 pr-4">Spec</th>
                    <th className="pb-2 pr-4">Why</th>
                    <th className="pb-2">Stored</th>
                  </tr>
                </thead>
                <tbody>
                  {exceptions.map((row) => (
                    <tr key={row.id} className="border-b last:border-0">
                      <td className="py-2 pr-4 font-mono">{row.product_code}</td>
                      <td className="py-2 pr-4">{row.spec_key}</td>
                      <td className="py-2 pr-4">{REASON_LABELS[row.reason] ?? row.reason}</td>
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

      <Card>
        <CardHeader>
          <CardTitle>Derived specifications ({total})</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={query}
              placeholder="Filter by product code or class"
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') load(query);
              }}
            />
            <Button variant="outline" onClick={() => load(query)}>
              Filter
            </Button>
          </div>

          {error && (
            <Alert variant="destructive">
              <AlertIcon />
              <AlertTitle>{error}</AlertTitle>
            </Alert>
          )}

          {loading && (
            <div className="flex flex-col gap-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          )}

          {!loading && rows.length === 0 && !error && (
            <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
              No derived specifications yet. Run the derivation job for a product class to
              populate this list.
            </div>
          )}

          {!loading && rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="pb-2 pr-4">Code</th>
                    <th className="pb-2 pr-4">Class</th>
                    <th className="pb-2 pr-4">Brand</th>
                    <th className="pb-2 pr-4">Specs</th>
                    <th className="pb-2">What search matches</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <Fragment key={row.product_id}>
                      <tr
                        className="border-b cursor-pointer hover:bg-muted/40"
                        onClick={() =>
                          setExpanded(expanded === row.product_id ? null : row.product_id)
                        }
                      >
                        <td className="py-2 pr-4 font-mono whitespace-nowrap">
                          {row.product_code}
                        </td>
                        <td className="py-2 pr-4 whitespace-nowrap">{row.class_label ?? '-'}</td>
                        <td className="py-2 pr-4 whitespace-nowrap">{row.brand_hint ?? '-'}</td>
                        <td className="py-2 pr-4 tabular-nums">
                          {row.spec_count}
                          {row.is_accessory && (
                            <Badge variant="secondary" size="sm" className="ml-2">
                              Accessory
                            </Badge>
                          )}
                          {row.is_discontinued && (
                            <Badge variant="warning" size="sm" className="ml-2">
                              Discontinued
                            </Badge>
                          )}
                          {row.open_exceptions > 0 && (
                            <Badge variant="destructive" size="sm" className="ml-2">
                              {row.open_exceptions} to check
                            </Badge>
                          )}
                        </td>
                        <td
                          className="py-2 text-muted-foreground max-w-md truncate"
                          title={row.rendered_text ?? ''}
                        >
                          {row.rendered_text ?? '-'}
                        </td>
                      </tr>
                      {expanded === row.product_id && (
                        <tr className="border-b bg-muted/20">
                          <td colSpan={5} className="p-4">
                            <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2">
                              Every value, and the text it was read from
                            </div>
                            <div className="grid gap-2 sm:grid-cols-2">
                              {Object.entries(row.values).map(([key, value]) => (
                                <div key={key} className="flex flex-wrap items-baseline gap-2">
                                  <span className="font-medium">{key.replace(/_/g, ' ')}:</span>
                                  <span className="font-mono">
                                    {String(value.value)}
                                    {value.unit ? ` ${value.unit}` : ''}
                                  </span>
                                  {row.provenance[key] && (
                                    <span className="text-xs text-muted-foreground">
                                      from &quot;{row.provenance[key].evidence}&quot; (
                                      {row.provenance[key].source})
                                    </span>
                                  )}
                                </div>
                              ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
