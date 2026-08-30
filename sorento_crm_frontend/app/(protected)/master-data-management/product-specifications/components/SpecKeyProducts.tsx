'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { Skeleton } from '@/components/ui/skeleton';
import { getSpecKeyProducts } from '../services/productSpecService';
import type { SpecKeyProducts as Products } from '../services/productSpecService';

const PAGE = 100;

/** Where a value came from, in the words the person reading this uses. */
const SOURCE_LABEL: Record<string, string> = {
  derived: 'Description',
  flyer: 'Flyer',
  code: 'Product code',
  category: 'Category',
  human: 'Set by hand',
};

/**
 * Every product carrying one specification, and the words each value was read from.
 *
 * A count is not reviewable. "Seen in 106" says something happened without saying to
 * what, and the only way to know a rule did what you meant is to look at the rows - a
 * drainer board on 74 bathtubs is invisible in a number and obvious the moment the
 * classes are tallied.
 */
export default function SpecKeyProducts({
  specKey,
  onClose,
}: {
  specKey: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<Products | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [value, setValue] = useState<string | undefined>();
  // `query` is what the request carries, one debounce behind the box: typing
  // straight into the request fires one round trip per keystroke against 22,805
  // rows.
  const {
    value: search,
    setValue: setSearch,
    debouncedValue: query,
    isSettling: searchSettling,
  } = useDebouncedSearch();

  // A narrower search is a different set, so page 1 is where it starts.
  useEffect(() => {
    setOffset(0);
  }, [query]);

  useEffect(() => {
    setLoading(true);
    getSpecKeyProducts(specKey, { limit: PAGE, offset, value, q: query || undefined })
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load the products'))
      .finally(() => setLoading(false));
  }, [specKey, offset, value, query]);

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertIcon />
        <AlertTitle>{error}</AlertTitle>
      </Alert>
    );
  }

  return (
    <div className="flex flex-col gap-4 rounded-md border bg-muted/20 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm">
          <span className="font-medium">{data?.label ?? specKey}</span>{' '}
          <span className="text-muted-foreground">
            on {data ? data.total.toLocaleString() : '…'} products
          </span>
        </div>
        <div className="flex items-center gap-2">
          <ListSearchInput
            className="w-64"
            value={search}
            onChange={setSearch}
            isSettling={searchSettling}
            placeholder="Find a code, description or value"
          />
          <Button size="sm" variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>

      {data && (
        <div className="flex flex-col gap-2 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="w-20 shrink-0 uppercase tracking-wide text-muted-foreground">
              Values
            </span>
            {value !== undefined && (
              <Button size="sm" variant="ghost" onClick={() => { setValue(undefined); setOffset(0); }}>
                Show all
              </Button>
            )}
            {data.by_value.map((row) => (
              <button
                key={String(row.value)}
                type="button"
                onClick={() => { setValue(String(row.value)); setOffset(0); }}
              >
                <Badge
                  variant={value === String(row.value) ? 'primary' : 'secondary'}
                  size="sm"
                  appearance="light"
                  shape="circle"
                >
                  {String(row.value)} · {row.count.toLocaleString()}
                </Badge>
              </button>
            ))}
          </div>
          {/* The tally that makes a wrong scope visible. */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="w-20 shrink-0 uppercase tracking-wide text-muted-foreground">
              Classes
            </span>
            {data.by_class.map((row) => (
              <Badge
                key={String(row.class)}
                variant="outline"
                size="sm"
                appearance="light"
                shape="circle"
              >
                {row.class ?? 'unclassed'} · {row.count.toLocaleString()}
              </Badge>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="w-20 shrink-0 uppercase tracking-wide text-muted-foreground">
              Read from
            </span>
            {data.by_source.map((row) => (
              <Badge
                key={String(row.source)}
                variant="outline"
                size="sm"
                appearance="light"
                shape="circle"
              >
                {SOURCE_LABEL[String(row.source)] ?? row.source ?? 'unknown'} ·{' '}
                {row.count.toLocaleString()}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {loading && <Skeleton className="h-40 w-full" />}

      {!loading && data && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="pb-2 pr-4">Code</th>
                <th className="pb-2 pr-4">Value</th>
                <th className="pb-2 pr-4">Class</th>
                <th className="pb-2 pr-4">Read from</th>
                <th className="pb-2 pr-4">Words it was read from</th>
                <th className="pb-2">Description</th>
              </tr>
            </thead>
            <tbody>
              {data.products.map((row) => (
                <tr key={row.id} className="border-b last:border-0 align-top">
                  <td className="py-2 pr-4 whitespace-nowrap font-mono text-xs">
                    <Link
                      href={`/master-data-management/products/${row.id}?tab=specifications`}
                      className="text-primary hover:underline"
                    >
                      {row.product_code}
                    </Link>
                  </td>
                  <td className="py-2 pr-4 whitespace-nowrap font-mono text-xs">
                    {String(row.value)}
                  </td>
                  <td className="py-2 pr-4 whitespace-nowrap text-muted-foreground">
                    {row.class ?? '-'}
                  </td>
                  <td className="py-2 pr-4 whitespace-nowrap text-muted-foreground">
                    {SOURCE_LABEL[String(row.source)] ?? row.source ?? '-'}
                  </td>
                  <td className="py-2 pr-4 whitespace-nowrap font-mono text-xs text-muted-foreground">
                    {row.evidence ?? '-'}
                  </td>
                  <td className="py-2 text-xs text-muted-foreground">{row.description}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {data.total > PAGE && (
            <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
              <Button
                size="sm"
                variant="outline"
                disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
              >
                Previous
              </Button>
              <span>
                {offset + 1} - {Math.min(offset + PAGE, data.total)} of{' '}
                {data.total.toLocaleString()}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={offset + PAGE >= data.total}
                onClick={() => setOffset((o) => o + PAGE)}
              >
                Next
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
