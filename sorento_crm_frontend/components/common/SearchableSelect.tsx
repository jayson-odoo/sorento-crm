'use client';

import * as React from 'react';
import { Check, ChevronDown, Loader2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import {
  selectTriggerVariants,
  type SelectTriggerSize,
} from '@/components/common/select-trigger-variants';

export type SearchableSelectOption = {
  value: string;
  label: string;
  /** Free-text used by the fuzzy filter (static mode); falls back to label + description. */
  searchText?: string;
  /** Optional secondary line under the label (e.g. customer code). */
  description?: string;
  /** Optional grouping header (renders one CommandGroup per distinct group). */
  group?: string;
  /** Per-option disabled (Radix `SelectItem disabled` parity). */
  disabled?: boolean;
};

export type SearchableSelectProps = {
  value: string;
  onChange: (value: string) => void;
  /**
   * The whole option that was just chosen, alongside `onChange`, and `null` when the selection
   * is cleared.
   *
   * For callers whose next step needs more than the id: an inline line table fills the rest of
   * the row from the picked product, and re-fetching a record it has just been handed would be
   * a round trip for data already on screen.
   */
  onOptionChange?: (option: SearchableSelectOption | null) => void;
  /** Static mode: full option set, filtered client-side. Mutually exclusive with `fetchOptions`. */
  options?: SearchableSelectOption[];
  /**
   * Async mode: server-search. Called with the popover search text (empty on open for the
   * first page), debounced 300ms. Results replace the list; stale responses are dropped.
   */
  fetchOptions?: (query: string, pageIndex: number) => Promise<SearchableSelectOption[]>;
  /**
   * Async mode: append pages instead of replacing, with a "Load more" row while the last
   * fetch came back full. Without this the list is whatever one page returns, which
   * quietly caps how much of a large catalog is reachable.
   */
  paginated?: boolean;
  /** Async + paginated: page size used to decide whether another page may exist. Default 50. */
  pageSize?: number;
  /**
   * Notified whenever the search text changes, in BOTH modes. Static-mode callers use this to
   * widen a locally-filtered list with a server refetch.
   */
  onSearchChange?: (query: string) => void;
  /**
   * Search text the popover opens with, for callers that already know what is being looked
   * for. It is put IN the search box rather than applied invisibly, so the user can see what
   * narrowed the list and widen it by editing or clearing the box. Restored on every open.
   */
  initialQuery?: string;
  /**
   * Async mode: the currently-selected option, so the trigger label + checkmark survive
   * when `value` isn't in the fetched page. Callers already hold the selected entity.
   */
  selectedOption?: SearchableSelectOption;
  /** When true, show an explicit × to clear to empty. Default false (required fields). */
  clearable?: boolean;
  /**
   * Size the menu to its options and WRAP a long label instead of truncating it.
   *
   * The default menu is exactly as wide as the trigger, and a label longer than
   * that is cut with an ellipsis - which in a narrow cell or filter popover can
   * make two options read identically. Opt in where the option text, not the
   * trigger, is what has to be readable.
   */
  wrapOptions?: boolean;
  /** Trigger size — shared with Radix SelectTrigger. Default `md`. */
  size?: SelectTriggerSize;
  /** Forwarded to the trigger so a <Label htmlFor> can point at it. */
  id?: string;
  placeholder?: string;
  emptyMessage?: string;
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
  /** Render the trigger label differently from the option label. */
  renderTriggerLabel?: (opt: SearchableSelectOption) => React.ReactNode;
  /** Render a custom option body (status dots, icons). Defaults to label + description. */
  renderOption?: (opt: SearchableSelectOption) => React.ReactNode;
  /**
   * Replace the whole trigger. For pickers that hang off something other than a select box —
   * an icon button, say — where the default trigger + chevron would be wrong.
   * Receives the resolved selection and open state; must render a single focusable element.
   */
  renderTrigger?: (state: {
    selected: SearchableSelectOption | null;
    open: boolean;
    disabled: boolean;
  }) => React.ReactNode;
  /**
   * A last row offering to create what was typed, for vocabularies a user may extend.
   *
   * Opt-in and absent by default, so every existing caller is untouched: a select over
   * customers or warehouses must never invite someone to invent one. `label` is called
   * with the trimmed search text; returning null suppresses the row for that text,
   * which is how a caller says "that word already exists under another name" without
   * this component needing to know the matching rules.
   */
  createOption?: {
    label: (query: string) => React.ReactNode | null;
    onCreate: (query: string) => void;
  };
};

export function SearchableSelect({
  value,
  onChange,
  onOptionChange,
  options,
  fetchOptions,
  selectedOption,
  clearable = false,
  wrapOptions = false,
  paginated = false,
  pageSize = 50,
  onSearchChange,
  initialQuery = '',
  id,
  size,
  placeholder = 'Select...',
  emptyMessage = 'No results found.',
  disabled = false,
  className,
  triggerClassName,
  renderTriggerLabel,
  renderOption,
  renderTrigger,
  createOption,
}: SearchableSelectProps) {
  const isAsync = typeof fetchOptions === 'function';
  const [open, setOpen] = React.useState(false);

  // Async state
  const [asyncOptions, setAsyncOptions] = React.useState<SearchableSelectOption[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [query, setQuery] = React.useState(initialQuery);
  const lastQueryRef = React.useRef<string>('\u0000'); // sentinel: never equals a real query

  const [page, setPage] = React.useState(0);
  const [hasMore, setHasMore] = React.useState(false);
  const [loadingMore, setLoadingMore] = React.useState(false);

  const runFetch = React.useCallback(
    async (q: string) => {
      if (!fetchOptions) return;
      lastQueryRef.current = q;
      setLoading(true);
      try {
        const items = await fetchOptions(q, 0);
        if (lastQueryRef.current !== q) return; // stale
        setAsyncOptions(items);
        setPage(0);
        setHasMore(paginated && items.length >= pageSize);
      } catch {
        if (lastQueryRef.current !== q) return;
        setAsyncOptions([]);
        setHasMore(false);
      } finally {
        if (lastQueryRef.current === q) setLoading(false);
      }
    },
    [fetchOptions, paginated, pageSize],
  );

  const loadMore = React.useCallback(async () => {
    if (!fetchOptions || loadingMore) return;
    const next = page + 1;
    setLoadingMore(true);
    try {
      const items = await fetchOptions(query, next);
      // A query change mid-flight invalidates this page.
      if (lastQueryRef.current !== query) return;
      setAsyncOptions((prev) => [...prev, ...items]);
      setPage(next);
      setHasMore(items.length >= pageSize);
    } catch {
      setHasMore(false);
    } finally {
      setLoadingMore(false);
    }
  }, [fetchOptions, loadingMore, page, query, pageSize]);

  // Eager first page on open; debounced fetch on query change (async mode only). A seeded
  // query is not a keystroke, it is what the caller already knew, so it fetches on open at
  // once rather than after the typing debounce.
  React.useEffect(() => {
    if (!isAsync || !open) return;
    const seeded = query === '' || query === initialQuery;
    const t = setTimeout(() => void runFetch(query), seeded ? 0 : 300);
    return () => clearTimeout(t);
  }, [isAsync, open, query, initialQuery, runFetch]);

  // Reset transient async state when the popover closes. Back to the seed, not to blank:
  // reopening asks the same question it asked the first time.
  React.useEffect(() => {
    if (open) return;
    setQuery(initialQuery);
    lastQueryRef.current = '\u0000';
  }, [open, initialQuery]);

  const baseOptions = React.useMemo(
    () => (isAsync ? asyncOptions : (options ?? [])),
    [isAsync, asyncOptions, options],
  );

  // Resolve the selected option for the trigger label + checkmark.
  const selected = React.useMemo(() => {
    if (!value) return null;
    const found = baseOptions.find((o) => o.value === value);
    if (found) return found;
    if (isAsync && selectedOption?.value === value) return selectedOption;
    return null;
  }, [baseOptions, value, isAsync, selectedOption]);

  // Static mode filters here rather than delegating to cmdk, so that (a) `onSearchChange`
  // callers see the same text the list is filtered by, and (b) matching is the same
  // all-tokens substring rule SearchableMultiSelect uses. cmdk's fuzzy subsequence scoring
  // surfaced loose matches ("kuala" hitting "North Dakota/Beulah"), which is hard to explain
  // and differed between the two halves of one standard. Async mode is filtered server-side.
  const visibleOptions = React.useMemo(() => {
    if (isAsync) return baseOptions;
    const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (tokens.length === 0) return baseOptions;
    return baseOptions.filter((opt) => {
      const haystack = (
        opt.searchText ?? `${opt.label} ${opt.description ?? ''}`
      ).toLowerCase();
      return tokens.every((t) => haystack.includes(t));
    });
  }, [isAsync, baseOptions, query]);

  const grouped = React.useMemo(() => {
    const map = new Map<string, SearchableSelectOption[]>();
    for (const opt of visibleOptions) {
      const key = opt.group ?? '';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(opt);
    }
    return Array.from(map.entries());
  }, [visibleOptions]);

  const misconfigured = !isAsync && options === undefined;
  const isDisabled = disabled || misconfigured;
  const showClear = clearable && !!value && !isDisabled;

  const select = (opt: SearchableSelectOption) => {
    onChange(opt.value);
    onOptionChange?.(opt);
    setOpen(false);
  };

  // Resolved once per render so the empty-state branch and the row itself cannot
  // disagree: without it, a query matching nothing renders "No results found." AND the
  // create row, which reads as the list contradicting itself.
  const createQuery = query.trim();
  const createLabel = createOption && createQuery ? createOption.label(createQuery) : null;

  const handleQueryChange = (q: string) => {
    setQuery(q);
    onSearchChange?.(q);
  };

  return (
    <Popover open={open} onOpenChange={(o) => !isDisabled && setOpen(o)}>
      <PopoverTrigger asChild>
        {renderTrigger ? (
          renderTrigger({ selected, open, disabled: isDisabled })
        ) : (
        <button
          type="button"
          disabled={isDisabled}
          id={id}
          data-slot="searchable-select-trigger"
          // Radix SelectTrigger exposes role=combobox; keep parity so callers and tests
          // can find the trigger by role, and screen readers announce expanded state.
          role="combobox"
          aria-expanded={open}
          className={cn(selectTriggerVariants({ size }), triggerClassName)}
        >
          <span className={cn('flex-1 truncate text-left', !selected && 'text-muted-foreground')}>
            {selected
              ? renderTriggerLabel
                ? renderTriggerLabel(selected)
                : selected.label
              : placeholder}
          </span>
          {showClear ? (
            <span
              role="button"
              tabIndex={-1}
              aria-label="Clear selection"
              className="shrink-0 rounded-sm opacity-60 hover:opacity-100"
              onPointerDown={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onChange('');
                onOptionChange?.(null);
              }}
            >
              <X className="size-4" />
            </span>
          ) : (
            <ChevronDown className="size-4 shrink-0 opacity-60 -me-0.5" />
          )}
        </button>
        )}
      </PopoverTrigger>
      {/* Portalled so a dialog's overflow can't clip the menu when it flips upward. */}
      <PopoverPortal>
      <PopoverContent
        className={cn(
            // Cap to the space Radix measured, or a long list makes the menu taller than
            // the viewport and the search box gets pushed off-screen on short windows.
            'max-h-(--radix-popper-available-height) flex flex-col p-0',
            wrapOptions
              ? // Grow to the widest option, never past the viewport, and never
                // narrower than the control it hangs off.
                'w-auto min-w-(--radix-popper-anchor-width) max-w-[min(28rem,calc(100vw-2rem))]'
              : // The menu follows its trigger's width but never goes below 16rem: a narrow
                // cell (a UOM column is 110px) made a legible list unreadable, one squeezed
                // word per line, and the column cannot be widened to suit its dropdown.
                // Capped at the space Radix measured so widening it can never push the menu
                // off a 375px screen.
                'w-[max(var(--radix-popper-anchor-width),16rem)] max-w-(--radix-popper-available-width)',
            className,
          )}
        align="start"
      >
        <Command shouldFilter={false} className="max-h-full min-h-0 flex flex-col">
          <CommandInput placeholder="Search..." value={query} onValueChange={handleQueryChange} />
          <CommandList className="min-h-0 flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center gap-2 px-3 py-3 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Searching...
              </div>
            ) : visibleOptions.length === 0 && !createLabel ? (
              <CommandEmpty>{emptyMessage}</CommandEmpty>
            ) : null}
            {grouped.map(([groupKey, opts]) => (
              <CommandGroup key={groupKey || '__ungrouped__'} heading={groupKey || undefined}>
                {opts.map((opt) => (
                  <CommandItem
                    key={opt.value}
                    value={opt.searchText ?? `${opt.label} ${opt.description ?? ''}`}
                    disabled={opt.disabled}
                    onSelect={() => select(opt)}
                    className="flex items-start gap-2"
                  >
                    <Check
                      className={cn(
                        'mt-0.5 size-4 shrink-0',
                        opt.value === value ? 'opacity-100' : 'opacity-0',
                      )}
                    />
                    {renderOption ? (
                      renderOption(opt)
                    ) : (
                      <div className="flex flex-1 flex-col min-w-0">
                        <span className={wrapOptions ? 'break-words' : 'truncate'}>
                          {opt.label}
                        </span>
                        {opt.description ? (
                          <span
                            className={cn(
                              'text-xs text-muted-foreground',
                              wrapOptions ? 'break-words' : 'truncate',
                            )}
                            title={opt.description}
                          >
                            {opt.description}
                          </span>
                        ) : null}
                      </div>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
            {createLabel ? (
              <div className="border-t p-1">
                <button
                  type="button"
                  data-slot="searchable-select-create"
                  onClick={() => {
                    createOption!.onCreate(createQuery);
                    setOpen(false);
                  }}
                  className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-start text-sm hover:bg-accent"
                >
                  {createLabel}
                </button>
              </div>
            ) : null}
            {hasMore ? (
              <div className="border-t p-1">
                <button
                  type="button"
                  data-slot="searchable-select-load-more"
                  onClick={() => void loadMore()}
                  disabled={loadingMore}
                  className="flex w-full items-center justify-center gap-2 rounded-sm px-2 py-1.5 text-sm text-muted-foreground hover:bg-accent disabled:opacity-60"
                >
                  {loadingMore ? <Loader2 className="size-4 animate-spin" /> : null}
                  {loadingMore ? 'Loading…' : 'Load more'}
                </button>
              </div>
            ) : null}
          </CommandList>
        </Command>
      </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
