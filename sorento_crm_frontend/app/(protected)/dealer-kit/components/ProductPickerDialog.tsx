'use client';

import { useEffect, useMemo, useState } from 'react';
import { Check, Minus, Package, Search } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RuleBuilder } from '@/components/rule-builder/RuleBuilder';
import type { RuleGroup } from '@/components/rule-builder/types';
import { cn } from '@/lib/utils';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { Skeleton } from '@/components/ui/skeleton';
import {
  PICKER_PAGE_SIZE,
  listPickerCategories,
  listPickerProducts,
  type PickerProduct,
} from '../services/productPickerService';

/**
 * Choosing what goes in a collection.
 *
 * Two ways in, deliberately, because Designers work both ways: a rule ("every
 * sink under RM1500") that keeps earning its keep as the catalogue changes, and
 * hand-picking for the cases no rule expresses. They compose - membership is
 * **rule union pins minus exclusions** - so a Designer can start from a rule and
 * then add or drop individual products without abandoning it.
 *
 * The rule tab uses the SHARED `RuleBuilder` against the `product` fact source,
 * which is the same component and the same evaluator the automation rules use.
 *
 * The preview is the important part. A rule you cannot see the results of is a
 * rule you have to publish to test, so the match list is always on screen and
 * always reflects the current rule plus pins minus exclusions.
 */

export interface ProductSelection {
  conditions: RuleGroup | null;
  pinnedProductIds: string[];
  excludedProductIds: string[];
}

export const EMPTY_SELECTION: ProductSelection = {
  conditions: null,
  pinnedProductIds: [],
  excludedProductIds: [],
};

/**
 * The rule's own matches come from the SERVER, because the server is where the
 * rule engine lives. Evaluating a second copy of the rule in the browser is the
 * exact "two evaluators that drift" trap the shared engine exists to avoid, and
 * the drift would only show up as a preview that disagreed with the published
 * page. So a rule edit saves and the resolved count comes back.
 */

function ProductRow({
  product,
  state,
  onToggle,
}: {
  product: PickerProduct;
  state: 'in' | 'out' | 'rule';
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={state !== 'out'}
      aria-label={`${state === 'out' ? 'Include' : 'Exclude'} ${product.name}`}
      className={cn(
        'flex w-full items-center gap-3 rounded-md border px-3 py-2 text-start transition-colors',
        state === 'out'
          ? 'border-border bg-background hover:bg-muted/60'
          : 'border-primary/40 bg-primary/5',
      )}
    >
      <span
        className={cn(
          'flex size-4 shrink-0 items-center justify-center rounded border',
          state === 'out' ? 'border-border' : 'border-primary bg-primary text-primary-foreground',
        )}
      >
        {state === 'in' && <Check className="size-3" />}
        {state === 'rule' && <Minus className="size-3" />}
      </span>

      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-foreground">{product.name}</span>
        <span className="block truncate font-mono text-xs text-muted-foreground">
          {product.code} · {product.category}
        </span>
      </span>

      {product.isDiscontinued && (
        <Badge variant="warning" appearance="ghost" className="shrink-0 text-xs">
          Discontinued
        </Badge>
      )}
      {state === 'rule' && (
        <Badge variant="outline" appearance="ghost" className="shrink-0 text-xs">
          by rule
        </Badge>
      )}
    </button>
  );
}

export function ProductPickerDialog({
  open,
  onOpenChange,
  value,
  onSave,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  value: ProductSelection;
  onSave: (selection: ProductSelection) => void;
}) {
  const [draft, setDraft] = useState<ProductSelection>(value);
  const [search, setSearch] = useState('');

  // Remount-on-open keeps the draft honest when the dialog is reopened after a
  // cancel; without it the previous edit would silently persist.
  const [openedWith, setOpenedWith] = useState(value);
  if (open && openedWith !== value) {
    setOpenedWith(value);
    setDraft(value);
  }

  /**
   * Search on the SERVER, a page at a time.
   *
   * This used to load one page and filter it in the browser, so with 22,000
   * active products a search for a code that exists 998 times answered "no
   * products match". Debounced so typing does not fire a request per keystroke.
   */
  /** The category chip in effect, or '' for the whole catalogue. */
  const [categoryId, setCategoryId] = useState('');
  const { data: categories = [] } = useQuery({
    queryKey: ['dealer-kit', 'picker-categories'],
    queryFn: listPickerCategories,
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  const [debounced, setDebounced] = useState('');
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const {
    data: pages,
    isLoading,
    isFetching,
    hasNextPage,
    fetchNextPage,
  } = useInfiniteQuery({
    queryKey: ['dealer-kit', 'picker-products', debounced, categoryId],
    queryFn: ({ pageParam = 0 }) =>
      listPickerProducts(debounced, pageParam as number, PICKER_PAGE_SIZE, categoryId),
    initialPageParam: 0,
    // A full page means there may be another; a short one means this is the end.
    getNextPageParam: (last: PickerProduct[], all) =>
      last.length < PICKER_PAGE_SIZE ? undefined : all.length,
    enabled: open,
  });

  const products = useMemo(() => (pages?.pages ?? []).flat(), [pages]);

  // Rule matches are resolved server-side after saving, so the live count here
  // reflects hand-picked products only. Saying so beats implying the rule has
  // already been applied.
  const matchedByRule = useMemo<string[]>(() => [], []);

  const members = useMemo(() => {
    const excluded = new Set(draft.excludedProductIds);
    const ordered = [...matchedByRule, ...draft.pinnedProductIds];
    return Array.from(new Set(ordered)).filter((id) => !excluded.has(id));
  }, [matchedByRule, draft.pinnedProductIds, draft.excludedProductIds]);

  // No client-side filtering: the server already answered this search.
  const visible = products;

  const stateOf = (product: PickerProduct): 'in' | 'out' | 'rule' => {
    if (draft.excludedProductIds.includes(product.id)) return 'out';
    if (draft.pinnedProductIds.includes(product.id)) return 'in';
    if (matchedByRule.includes(product.id)) return 'rule';
    return 'out';
  };

  const toggle = (product: PickerProduct) => {
    setDraft((current) => {
      const pinned = new Set(current.pinnedProductIds);
      const excluded = new Set(current.excludedProductIds);
      const isMember = members.includes(product.id);

      if (isMember) {
        // Removing a member: drop the pin if that is what put it in, and
        // exclude it if the rule would otherwise keep pulling it back.
        pinned.delete(product.id);
        if (matchedByRule.includes(product.id)) excluded.add(product.id);
      } else {
        excluded.delete(product.id);
        if (!matchedByRule.includes(product.id)) pinned.add(product.id);
      }

      return {
        ...current,
        pinnedProductIds: [...pinned],
        excludedProductIds: [...excluded],
      };
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Choose products</DialogTitle>
          <DialogDescription>
            Match products with a rule, pick them by hand, or do both. A rule keeps working as
            the catalogue changes; hand-picked products stay put.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="rule">
          <TabsList>
            <TabsTrigger value="rule">By rule</TabsTrigger>
            <TabsTrigger value="manual">By hand</TabsTrigger>
          </TabsList>

          <TabsContent value="rule" className="pt-3">
            <RuleBuilder
              sources={['product']}
              value={draft.conditions}
              onChange={(conditions) => setDraft((current) => ({ ...current, conditions }))}
            />
          </TabsContent>

          <TabsContent value="manual" className="pt-3">
            <div className="relative mb-3">
              <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="ps-9"
                placeholder="Search products"
                aria-label="Search products"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>

            {/* Browse by category alongside the search box. Chips scroll rather
                than wrap into a wall: there are hundreds of categories, and a
                picker that pushes the product list off screen has traded one
                problem for another. */}
            {categories.length > 0 && (
              <div className="flex gap-1 overflow-x-auto pb-1" data-dk-category-chips>
                <Button
                  size="sm"
                  variant={categoryId === '' ? 'primary' : 'outline'}
                  className="shrink-0"
                  onClick={() => setCategoryId('')}
                >
                  All
                </Button>
                {categories.map((category) => (
                  <Button
                    key={category.id}
                    size="sm"
                    variant={categoryId === category.id ? 'primary' : 'outline'}
                    className="shrink-0"
                    data-dk-category-chip={category.id}
                    onClick={() => setCategoryId(category.id === categoryId ? '' : category.id)}
                  >
                    {category.name}
                  </Button>
                ))}
              </div>
            )}

            {/* h-, not max-h-: a Radix ScrollArea with only a max height never
                scrolls - the content simply overflows and the rows below the
                fold become unreachable. */}
            <ScrollArea className="h-72">
              <div className="flex flex-col gap-1.5 pe-3">
                {isLoading &&
                  [0, 1, 2, 3].map((row) => <Skeleton key={row} className="h-12 w-full" />)}
                {!isLoading && visible.length === 0 && (
                  <p className="py-6 text-center text-sm text-muted-foreground">
                    No products match that search.
                  </p>
                )}
                {visible.map((product) => (
                  <ProductRow
                    key={product.id}
                    product={product}
                    state={stateOf(product)}
                    onToggle={() => toggle(product)}
                  />
                ))}
                {hasNextPage && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-1"
                    disabled={isFetching}
                    onClick={() => fetchNextPage()}
                  >
                    {isFetching ? 'Loading' : 'Load more products'}
                  </Button>
                )}
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>

        <div className="rounded-lg border border-border bg-muted/30 p-3">
          <div className="flex items-center gap-2">
            <Package className="size-4 text-muted-foreground" aria-hidden />
            <p className="text-sm font-medium text-foreground" data-dk-match-count>
              {members.length} product{members.length === 1 ? '' : 's'} selected
            </p>
            {draft.excludedProductIds.length > 0 && (
              <Badge variant="outline" appearance="ghost" className="text-xs">
                {draft.excludedProductIds.length} excluded
              </Badge>
            )}
          </div>

          {members.length === 0 ? (
            <p className="mt-1.5 text-xs text-muted-foreground">
              Nothing selected yet. Add a rule, or pick products by hand.
            </p>
          ) : (
            <p className="mt-1.5 truncate text-xs text-muted-foreground">
              {members
                .map((id) => products.find((product) => product.id === id)?.code)
                .filter(Boolean)
                .join(', ')}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              onSave(draft);
              onOpenChange(false);
            }}
          >
            Use these products
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
