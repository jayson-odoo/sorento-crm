'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  getCoreRowModel,
  getExpandedRowModel,
  useReactTable,
  type ColumnDef,
  type ExpandedState,
} from '@tanstack/react-table';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  getKeysForProduct,
  getSpecCoverage,
  getSpecRegistry,
} from '../services/productSpecService';
import type { ProductSpecKey } from '../services/productSpecService';
import type { SpecRegistryKey } from '../types/productSpec.types';
import AddSpecKey from './AddSpecKey';
import CatalogueFreshness from './CatalogueFreshness';
import PillList from './PillList';
import SpecKeyEditor from './SpecKeyEditor';
import SpecKeyProducts from './SpecKeyProducts';

/**
 * Every spec key the system knows, and every word that resolves onto it.
 *
 * This IS the extraction prompt the n8n parser reads and the vocabulary the ranker's
 * word-resolver matches against - not a description of it. If a phrase isn't reaching
 * a product, this table says whether the word simply isn't bound to anything yet.
 *
 * Built on the system's DataGrid rather than a hand-rolled table, so the type scale,
 * header treatment and row rhythm match every other list in the product. A bespoke
 * table here read as a different application.
 */
export default function SpecRegistryTable() {
  const [keys, setKeys] = useState<SpecRegistryKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [inspecting, setInspecting] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [savedCount, setSavedCount] = useState(0);
  const [filter, setFilter] = useState('');
  const [expanded, setExpanded] = useState<ExpandedState>({});
  // When the filter names a real product code, the table narrows to the keys THAT
  // PRODUCT carries. "Why does this code not come back for rimless" is asked about a
  // code, and answering it meant opening the product page in another tab.
  const [productKeys, setProductKeys] = useState<Record<string, ProductSpecKey> | null>(null);
  const [matchedCode, setMatchedCode] = useState<string | null>(null);
  // The live count, which is not `measured_coverage`: that is a note made when the key
  // was written, and it goes out of date the first time anyone edits a rule.
  const [coverage, setCoverage] = useState<Record<string, number>>({});

  useEffect(() => {
    getSpecRegistry()
      .then((r) => setKeys(r.keys))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  // Refreshed after every save, because a rule edit is exactly what changes it.
  useEffect(() => {
    getSpecCoverage()
      .then((r) => setCoverage(r.coverage))
      .catch(() => setCoverage({}));
  }, [savedCount]);

  // A filter that looks like a product code is looked up as one. Anything with a digit
  // is worth asking about; a word like "chrome" never reaches the server.
  useEffect(() => {
    const candidate = filter.trim();
    if (candidate.length < 3 || !/\d/.test(candidate)) {
      setProductKeys(null);
      setMatchedCode(null);
      return;
    }
    const timer = setTimeout(() => {
      getKeysForProduct(candidate)
        .then((r) => {
          setProductKeys(r.matched_product ? r.keys : null);
          setMatchedCode(r.matched_product?.product_code ?? null);
        })
        .catch(() => {
          setProductKeys(null);
          setMatchedCode(null);
        });
    }, 300);
    return () => clearTimeout(timer);
  }, [filter]);

  const allSynonyms = (key: SpecRegistryKey): string[] => {
    if (key.data_type === 'boolean') {
      return Array.from(new Set(key.synonyms?.true ?? []));
    }
    return Array.from(new Set(Object.values(key.synonyms ?? {}).flat()));
  };

  /**
   * Words that resolve to more than one value of the SAME key.
   *
   * "free standing" was added to `free_standing` while the seed already had it on
   * `floor_standing`, so the word now means two things and the resolver takes whichever
   * it reaches first. The list rendered it twice and said nothing - a word doing two
   * jobs is worth naming, not de-duplicating quietly.
   */
  const ambiguousWords = (key: SpecRegistryKey): string[] => {
    const owners = new Map<string, Set<string>>();
    for (const [value, words] of Object.entries(key.synonyms ?? {})) {
      for (const word of words) {
        if (!owners.has(word)) owners.set(word, new Set());
        owners.get(word)!.add(value);
      }
    }
    return [...owners.entries()].filter(([, values]) => values.size > 1).map(([word]) => word);
  };

  const visible = useMemo(
    () =>
      keys.filter((key) => {
        const needle = filter.trim().toLowerCase();
        if (!needle) return true;
        // A matched product wins over word matching: you asked about a code, so the
        // answer is that code's specs, not every key whose wording contains the digits.
        if (productKeys) return key.spec_key in productKeys;
        const words = Object.entries(key.synonyms ?? {}).flatMap(([value, list]) => [
          value,
          ...list,
        ]);
        return [key.spec_key, key.label, ...key.allowed_values, ...words]
          .join(' ')
          .toLowerCase()
          .includes(needle);
      }),
    [keys, filter, productKeys],
  );

  const onSaved = (updated: SpecRegistryKey) => {
    setKeys((current) => current.map((k) => (k.spec_key === updated.spec_key ? updated : k)));
    setEditing(null);
    setExpanded({});
    setSavedCount((n) => n + 1);
  };

  /** Only one row is ever open, and it opens onto exactly one of the two panels. */
  const toggle = (specKey: string, mode: 'edit' | 'products') => {
    const alreadyOpen =
      (mode === 'edit' && editing === specKey) ||
      (mode === 'products' && inspecting === specKey);
    setEditing(mode === 'edit' && !alreadyOpen ? specKey : null);
    setInspecting(mode === 'products' && !alreadyOpen ? specKey : null);
    setExpanded(alreadyOpen ? {} : { [specKey]: true });
  };

  const columns = useMemo<ColumnDef<SpecRegistryKey>[]>(() => {
    const base: ColumnDef<SpecRegistryKey>[] = [
      {
        id: 'key',
        accessorFn: (row) => row.label,
        header: ({ column }) => <DataGridColumnHeader title="Key" column={column} />,
        size: 210,
        enableSorting: false,
        meta: {
          headerTitle: 'Key',
          skeleton: <Skeleton className="h-4 w-28" />,
          // One column owns the expanded panel; the grid finds it by this field.
          expandedContent: (key: SpecRegistryKey) =>
            editing === key.spec_key ? (
              <SpecKeyEditor
                specKey={key}
                onSaved={onSaved}
                onCancel={() => {
                  setEditing(null);
                  setExpanded({});
                }}
              />
            ) : inspecting === key.spec_key ? (
              <SpecKeyProducts
                specKey={key.spec_key}
                onClose={() => {
                  setInspecting(null);
                  setExpanded({});
                }}
              />
            ) : null,
        },
        cell: ({ row }) => (
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <span className="font-medium">{row.original.label}</span>
              {!row.original.is_active && (
                <Badge variant="secondary" size="sm" appearance="light" shape="circle">
                  Off
                </Badge>
              )}
              {row.original.source === 'user' && (
                <Badge variant="primary" size="sm" appearance="light" shape="circle">
                  Yours
                </Badge>
              )}
            </div>
            <span className="font-mono text-xs text-muted-foreground">
              {row.original.spec_key}
            </span>
          </div>
        ),
      },
      {
        id: 'type',
        accessorFn: (row) => row.data_type,
        header: ({ column }) => <DataGridColumnHeader title="Type" column={column} />,
        size: 120,
        enableSorting: false,
        meta: { headerTitle: 'Type', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) => (
          <span className="text-muted-foreground">
            {row.original.data_type}
            {row.original.unit ? ` (${row.original.unit})` : ''}
          </span>
        ),
      },
      {
        id: 'applies_to',
        accessorFn: (row) => Object.values(row.applies_when ?? {}).flat().join(', '),
        header: ({ column }) => <DataGridColumnHeader title="Applies to" column={column} />,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Applies to', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => {
          const gate = Object.entries(row.original.applies_when ?? {});
          return (
            <span className="text-muted-foreground">
              {gate.length > 0
                ? gate.map(([, values]) => values.join(', ')).join('; ')
                : 'Every class'}
            </span>
          );
        },
      },
      {
        id: 'weight',
        accessorFn: (row) => row.rank_weight,
        header: ({ column }) => <DataGridColumnHeader title="Weight" column={column} />,
        size: 90,
        enableSorting: false,
        meta: { headerTitle: 'Weight', skeleton: <Skeleton className="h-4 w-8" /> },
        cell: ({ row }) => (
          <span className="tabular-nums text-muted-foreground">
            {row.original.rank_weight ?? '-'}
          </span>
        ),
      },
      {
        id: 'seen_in',
        accessorFn: (row) => coverage[row.spec_key] ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="Seen in" column={column} />,
        size: 100,
        enableSorting: false,
        meta: { headerTitle: 'Seen in', skeleton: <Skeleton className="h-4 w-12" /> },
        // Clickable, because the count is the question and the rows are the answer:
        // "seen in 106" cannot tell you whether the rule read what you meant.
        cell: ({ row }) =>
          coverage[row.original.spec_key] ? (
            <button
              type="button"
              className="tabular-nums text-primary hover:underline"
              onClick={() => toggle(row.original.spec_key, 'products')}
            >
              {coverage[row.original.spec_key].toLocaleString()}
            </button>
          ) : (
            <span className="text-muted-foreground"> - </span>
          ),
      },
    ];

    if (productKeys) {
      base.push({
        id: 'this_product',
        accessorFn: (row) => String(productKeys[row.spec_key]?.value ?? ''),
        header: ({ column }) => <DataGridColumnHeader title="This product" column={column} />,
        size: 150,
        enableSorting: false,
        meta: { headerTitle: 'This product', skeleton: <Skeleton className="h-4 w-16" /> },
        cell: ({ row }) => (
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-xs">
              {String(productKeys[row.original.spec_key]?.value ?? '-')}
            </span>
            {productKeys[row.original.spec_key]?.source && (
              <span className="text-xs text-muted-foreground">
                {productKeys[row.original.spec_key]?.source}
              </span>
            )}
          </div>
        ),
      });
    }

    base.push(
      {
        id: 'words',
        accessorFn: (row) => allSynonyms(row).join(', '),
        header: ({ column }) => (
          <DataGridColumnHeader title="Words that resolve to it" column={column} />
        ),
        size: 400,
        enableSorting: false,
        meta: {
          headerTitle: 'Words that resolve to it',
          skeleton: <Skeleton className="h-4 w-52" />,
        },
        cell: ({ row }) => {
          const synonyms = allSynonyms(row.original);
          const ambiguous = ambiguousWords(row.original);
          if (synonyms.length > 0) {
            return (
              <div className="flex flex-col gap-1">
                {/* Capped, with the rest behind a +N. `finish` carries 17 words and
                    `product_type` 31 values; in full, one row was three lines tall. */}
                <PillList
                  values={synonyms}
                  emphasis={ambiguous}
                  ariaLabel={`Words that resolve to ${row.original.label}`}
                />
                {ambiguous.length > 0 && (
                  <p className="text-xs text-warning">
                    {ambiguous.map((w) => `"${w}"`).join(', ')} resolves to more than one
                    value of this specification, so a customer saying it gets whichever is
                    reached first. Remove it from one of them.
                  </p>
                )}
              </div>
            );
          }
          if (row.original.allowed_values.length > 0) {
            return (
              <span className="text-muted-foreground">
                {row.original.allowed_values.join(', ')}
                <span className="italic"> (no synonyms bound yet)</span>
              </span>
            );
          }
          // "Open vocabulary, sourced from the catalog" said nothing a person could act
          // on: it named a property of the data model rather than what to do about it.
          return (
            <span className="text-muted-foreground">
              No fixed list - every value the catalogue holds counts.
              <span className="italic"> Edit to add customer wording.</span>
            </span>
          );
        },
      },
      {
        id: 'actions',
        header: '',
        size: 90,
        enableSorting: false,
        meta: { headerTitle: '', skeleton: <Skeleton className="h-8 w-16" /> },
        cell: ({ row }) => (
          <Button
            variant="outline"
            size="sm"
            onClick={() => toggle(row.original.spec_key, 'edit')}
          >
            {editing === row.original.spec_key ? 'Close' : 'Edit'}
          </Button>
        ),
      },
    );

    return base;
  }, [coverage, editing, inspecting, productKeys]);

  const table = useReactTable({
    columns,
    data: visible,
    getRowId: (row) => row.spec_key,
    state: {
      expanded,
      // Every key on one page: this is a 37-row vocabulary that people scan and search,
      // not a feed to page through.
      pagination: { pageIndex: 0, pageSize: Math.max(visible.length, 1) },
    },
    onExpandedChange: setExpanded,
    getRowCanExpand: (row) =>
      editing === row.original.spec_key || inspecting === row.original.spec_key,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
  });

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertIcon />
        <AlertTitle>{error}</AlertTitle>
      </Alert>
    );
  }

  return (
    <DataGrid
      table={table}
      recordCount={visible.length}
      isLoading={loading}
      emptyMessage="No specifications match."
      tableLayout={{ width: 'fixed', rowBorder: true }}
    >
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <span className="text-base font-semibold">
            Spec keys supported (
            {filter.trim() ? `${visible.length} of ${keys.length}` : keys.length})
          </span>
          <div className="flex items-center gap-2">
            <Input
              className="h-8 w-72"
              value={filter}
              placeholder="Find a spec, word or product code"
              aria-label="Find a spec, word or product code"
              onChange={(e) => setFilter(e.target.value)}
            />
            <Button variant="outline" size="sm" onClick={() => setAdding(true)} disabled={adding}>
              Add a specification
            </Button>
          </div>
        </CardHeader>

        <div className="px-5 pb-3">
          <CatalogueFreshness refreshKey={savedCount} />
          <AddSpecKey
            open={adding}
            onOpenChange={setAdding}
            onCreated={(created) => {
              setKeys((current) => [...current, created]);
              // Straight into the editor: a key with no rules reads nothing, so the
              // next step is never optional.
              setEditing(created.spec_key);
              setExpanded({ [created.spec_key]: true });
            }}
          />
          {matchedCode && (
            <p className="text-sm text-muted-foreground">
              Showing the {visible.length} specification{visible.length === 1 ? '' : 's'}{' '}
              <span className="font-mono">{matchedCode}</span> carries.
            </p>
          )}
        </div>

        <DataGridTable />
      </Card>
    </DataGrid>
  );
}
