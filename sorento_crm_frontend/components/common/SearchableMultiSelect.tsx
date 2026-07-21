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
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  selectTriggerVariants,
  type SelectTriggerSize,
} from '@/components/common/select-trigger-variants';

export type SearchableMultiSelectOption = {
  value: string;
  label: string;
  /** Optional grouping header (renders one CommandGroup per distinct group). */
  group?: string;
  /** Free-text used by the fuzzy filter (static mode); falls back to label + description. */
  searchText?: string;
  /** Optional secondary line under the label. */
  description?: string;
  /** When set, render a small badge after the label (e.g. "owned by X"). */
  badgeText?: string;
  /** Per-option disabled. */
  disabled?: boolean;
};

export type SearchableMultiSelectProps = {
  value: string[];
  onChange: (value: string[]) => void;
  /** Static mode: full option set, filtered client-side. Mutually exclusive with `fetchOptions`. */
  options?: SearchableMultiSelectOption[];
  /** Async mode: server-search, debounced 300ms, stale-dropped. Empty query on open = first page. */
  fetchOptions?: (query: string) => Promise<SearchableMultiSelectOption[]>;
  /**
   * Async mode: the currently-selected options, so trigger chips + checkmarks survive when the
   * selected values aren't in the fetched page.
   */
  selectedOptions?: SearchableMultiSelectOption[];
  /** Trigger size — shared with Radix SelectTrigger. Default `md`. */
  size?: SelectTriggerSize;
  placeholder?: string;
  emptyMessage?: string;
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
  /** Override the trigger body entirely (default = removable chips). */
  renderTriggerLabel?: (selected: SearchableMultiSelectOption[]) => React.ReactNode;
};

export function SearchableMultiSelect({
  value,
  onChange,
  options,
  fetchOptions,
  selectedOptions,
  size,
  placeholder = 'Select...',
  emptyMessage = 'No results found.',
  disabled = false,
  className,
  triggerClassName,
  renderTriggerLabel,
}: SearchableMultiSelectProps) {
  const isAsync = typeof fetchOptions === 'function';
  const [open, setOpen] = React.useState(false);

  const [asyncOptions, setAsyncOptions] = React.useState<SearchableMultiSelectOption[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [query, setQuery] = React.useState('');
  const lastQueryRef = React.useRef<string>(' ');

  const runFetch = React.useCallback(
    async (q: string) => {
      if (!fetchOptions) return;
      lastQueryRef.current = q;
      setLoading(true);
      try {
        const items = await fetchOptions(q);
        if (lastQueryRef.current !== q) return;
        setAsyncOptions(items);
      } catch {
        if (lastQueryRef.current !== q) return;
        setAsyncOptions([]);
      } finally {
        if (lastQueryRef.current === q) setLoading(false);
      }
    },
    [fetchOptions],
  );

  React.useEffect(() => {
    if (!isAsync || !open) return;
    const t = setTimeout(() => void runFetch(query), query === '' ? 0 : 300);
    return () => clearTimeout(t);
  }, [isAsync, open, query, runFetch]);

  React.useEffect(() => {
    if (open) return;
    setQuery('');
    lastQueryRef.current = ' ';
  }, [open]);

  const baseOptions = React.useMemo(
    () => (isAsync ? asyncOptions : (options ?? [])),
    [isAsync, asyncOptions, options],
  );
  const selectedSet = React.useMemo(() => new Set(value), [value]);

  // Resolve selected options for chips: prefer fetched/static, fall back to selectedOptions prop.
  const chosen = React.useMemo(() => {
    const byValue = new Map<string, SearchableMultiSelectOption>();
    for (const o of baseOptions) if (selectedSet.has(o.value)) byValue.set(o.value, o);
    if (isAsync) {
      for (const o of selectedOptions ?? []) {
        if (selectedSet.has(o.value) && !byValue.has(o.value)) byValue.set(o.value, o);
      }
    }
    // Preserve `value` ordering; unknown values render as bare chips.
    return value.map((v) => byValue.get(v) ?? { value: v, label: v });
  }, [baseOptions, selectedSet, isAsync, selectedOptions, value]);

  // Static mode filters here rather than delegating to cmdk, because Select all must act on
  // exactly the rows the user can see — and cmdk never tells us which those are. Async mode is
  // already filtered server-side, so its options pass through untouched.
  const visibleOptions = React.useMemo(() => {
    if (isAsync) return baseOptions;
    const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (tokens.length === 0) return baseOptions;
    return baseOptions.filter((opt) => {
      const haystack = (
        opt.searchText ?? `${opt.label} ${opt.description ?? ''} ${opt.badgeText ?? ''}`
      ).toLowerCase();
      return tokens.every((t) => haystack.includes(t));
    });
  }, [isAsync, baseOptions, query]);

  const grouped = React.useMemo(() => {
    const map = new Map<string, SearchableMultiSelectOption[]>();
    for (const opt of visibleOptions) {
      const key = opt.group ?? '';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(opt);
    }
    return Array.from(map.entries());
  }, [visibleOptions]);

  // Select all targets the visible, non-disabled rows only — never a disabled option, and never
  // a row the active search has filtered out.
  const selectable = React.useMemo(
    () => visibleOptions.filter((o) => !o.disabled),
    [visibleOptions],
  );
  const allVisibleSelected =
    selectable.length > 0 && selectable.every((o) => selectedSet.has(o.value));

  const isFiltered = !isAsync && query.trim().length > 0;
  const selectAllLabel = allVisibleSelected
    ? isFiltered
      ? `Clear ${selectable.length} matching`
      : 'Clear all'
    : isFiltered
      ? `Select ${selectable.length} matching`
      : isAsync
        ? // Async only ever holds the loaded page, so promising "all" would be a lie.
          `Select all ${selectable.length} loaded`
        : `Select all (${selectable.length})`;

  const toggleAll = () => {
    const visibleValues = selectable.map((o) => o.value);
    if (allVisibleSelected) {
      const drop = new Set(visibleValues);
      onChange(value.filter((v) => !drop.has(v)));
    } else {
      const merged = [...value];
      const have = new Set(value);
      for (const v of visibleValues) if (!have.has(v)) merged.push(v);
      onChange(merged);
    }
  };

  const misconfigured = !isAsync && options === undefined;
  const isDisabled = disabled || misconfigured;

  const toggle = (v: string) => {
    if (selectedSet.has(v)) onChange(value.filter((x) => x !== v));
    else onChange([...value, v]);
  };
  const remove = (v: string) => onChange(value.filter((x) => x !== v));

  return (
    <Popover open={open} onOpenChange={(o) => !isDisabled && setOpen(o)}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={isDisabled}
          data-slot="searchable-multi-select-trigger"
          className={cn(
            selectTriggerVariants({ size }),
            // Chips grow the trigger vertically; keep border/focus identical, drop the fixed height.
            'h-auto min-h-8.5 flex-wrap gap-1 py-1',
            triggerClassName,
          )}
        >
          {renderTriggerLabel ? (
            <span className="flex-1 text-left">{renderTriggerLabel(chosen)}</span>
          ) : chosen.length === 0 ? (
            <span className="flex-1 truncate text-left text-muted-foreground">{placeholder}</span>
          ) : (
            <span className="flex flex-1 flex-wrap gap-1">
              {chosen.map((opt) => (
                <span
                  key={opt.value}
                  className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-xs"
                >
                  <span className="truncate">{opt.label}</span>
                  <span
                    role="button"
                    tabIndex={-1}
                    aria-label={`Remove ${opt.label}`}
                    className="opacity-60 hover:opacity-100"
                    onPointerDown={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      remove(opt.value);
                    }}
                  >
                    <X className="size-3" />
                  </span>
                </span>
              ))}
            </span>
          )}
          <ChevronDown className="size-4 shrink-0 self-start mt-1 opacity-60 -me-0.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent className={cn('w-(--radix-popper-anchor-width) p-0', className)} align="start">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Search..." value={query} onValueChange={setQuery} />
          {!loading && selectable.length > 0 ? (
            <div className="border-b p-1">
              <button
                type="button"
                data-slot="searchable-multi-select-all"
                onClick={toggleAll}
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent"
              >
                <div className="flex size-4 items-center justify-center rounded-sm border border-input">
                  {allVisibleSelected ? <Check className="size-3" /> : null}
                </div>
                <span className="flex-1 text-left font-medium">{selectAllLabel}</span>
              </button>
            </div>
          ) : null}
          <CommandList>
            {loading ? (
              <div className="flex items-center gap-2 px-3 py-3 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Searching...
              </div>
            ) : visibleOptions.length === 0 ? (
              <CommandEmpty>{emptyMessage}</CommandEmpty>
            ) : null}
            {grouped.map(([groupKey, opts]) => (
              <CommandGroup key={groupKey || '__ungrouped__'} heading={groupKey || undefined}>
                {opts.map((opt) => {
                  const isSelected = selectedSet.has(opt.value);
                  return (
                    <CommandItem
                      key={opt.value}
                      // Filtering is ours now, so this only has to be unique — two options
                      // sharing a label would otherwise collide in cmdk's keyboard nav.
                      value={opt.value}
                      disabled={opt.disabled}
                      onSelect={() => toggle(opt.value)}
                      className="flex items-start gap-2"
                    >
                      <div className="mt-0.5 flex size-4 items-center justify-center rounded-sm border border-input">
                        {isSelected ? <Check className="size-3" /> : null}
                      </div>
                      <div className="flex flex-1 flex-col">
                        <div className="flex items-center gap-2">
                          <span>{opt.label}</span>
                          {opt.badgeText ? (
                            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-900">
                              {opt.badgeText}
                            </span>
                          ) : null}
                        </div>
                        {opt.description ? (
                          <span className="truncate text-xs text-muted-foreground" title={opt.description}>
                            {opt.description}
                          </span>
                        ) : null}
                      </div>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
