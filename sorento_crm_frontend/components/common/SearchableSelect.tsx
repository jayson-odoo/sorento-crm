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
  /** Static mode: full option set, filtered client-side. Mutually exclusive with `fetchOptions`. */
  options?: SearchableSelectOption[];
  /**
   * Async mode: server-search. Called with the popover search text (empty on open for the
   * first page), debounced 300ms. Results replace the list; stale responses are dropped.
   */
  fetchOptions?: (query: string) => Promise<SearchableSelectOption[]>;
  /**
   * Async mode: the currently-selected option, so the trigger label + checkmark survive
   * when `value` isn't in the fetched page. Callers already hold the selected entity.
   */
  selectedOption?: SearchableSelectOption;
  /** When true, show an explicit × to clear to empty. Default false (required fields). */
  clearable?: boolean;
  /** Trigger size — shared with Radix SelectTrigger. Default `md`. */
  size?: SelectTriggerSize;
  placeholder?: string;
  emptyMessage?: string;
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
  /** Render the trigger label differently from the option label. */
  renderTriggerLabel?: (opt: SearchableSelectOption) => React.ReactNode;
  /** Render a custom option body (status dots, icons). Defaults to label + description. */
  renderOption?: (opt: SearchableSelectOption) => React.ReactNode;
};

export function SearchableSelect({
  value,
  onChange,
  options,
  fetchOptions,
  selectedOption,
  clearable = false,
  size,
  placeholder = 'Select...',
  emptyMessage = 'No results found.',
  disabled = false,
  className,
  triggerClassName,
  renderTriggerLabel,
  renderOption,
}: SearchableSelectProps) {
  const isAsync = typeof fetchOptions === 'function';
  const [open, setOpen] = React.useState(false);

  // Async state
  const [asyncOptions, setAsyncOptions] = React.useState<SearchableSelectOption[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [query, setQuery] = React.useState('');
  const lastQueryRef = React.useRef<string>('\u0000'); // sentinel: never equals a real query

  const runFetch = React.useCallback(
    async (q: string) => {
      if (!fetchOptions) return;
      lastQueryRef.current = q;
      setLoading(true);
      try {
        const items = await fetchOptions(q);
        if (lastQueryRef.current !== q) return; // stale
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

  // Eager first page on open; debounced fetch on query change (async mode only).
  React.useEffect(() => {
    if (!isAsync || !open) return;
    const t = setTimeout(() => void runFetch(query), query === '' ? 0 : 300);
    return () => clearTimeout(t);
  }, [isAsync, open, query, runFetch]);

  // Reset transient async state when the popover closes.
  React.useEffect(() => {
    if (open) return;
    setQuery('');
    lastQueryRef.current = '\u0000';
  }, [open]);

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

  const grouped = React.useMemo(() => {
    const map = new Map<string, SearchableSelectOption[]>();
    for (const opt of baseOptions) {
      const key = opt.group ?? '';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(opt);
    }
    return Array.from(map.entries());
  }, [baseOptions]);

  const misconfigured = !isAsync && options === undefined;
  const isDisabled = disabled || misconfigured;
  const showClear = clearable && !!value && !isDisabled;

  const select = (v: string) => {
    onChange(v);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={(o) => !isDisabled && setOpen(o)}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={isDisabled}
          data-slot="searchable-select-trigger"
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
              }}
            >
              <X className="size-4" />
            </span>
          ) : (
            <ChevronDown className="size-4 shrink-0 opacity-60 -me-0.5" />
          )}
        </button>
      </PopoverTrigger>
      {/* Portalled so a dialog's overflow can't clip the menu when it flips upward. */}
      <PopoverPortal>
      <PopoverContent
        className={cn('w-(--radix-popper-anchor-width) p-0', className)}
        align="start"
      >
        <Command shouldFilter={!isAsync}>
          <CommandInput
            placeholder="Search..."
            value={isAsync ? query : undefined}
            onValueChange={isAsync ? setQuery : undefined}
          />
          <CommandList>
            {loading ? (
              <div className="flex items-center gap-2 px-3 py-3 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Searching...
              </div>
            ) : (
              <CommandEmpty>{emptyMessage}</CommandEmpty>
            )}
            {grouped.map(([groupKey, opts]) => (
              <CommandGroup key={groupKey || '__ungrouped__'} heading={groupKey || undefined}>
                {opts.map((opt) => (
                  <CommandItem
                    key={opt.value}
                    value={opt.searchText ?? `${opt.label} ${opt.description ?? ''}`}
                    disabled={opt.disabled}
                    onSelect={() => select(opt.value)}
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
                      <div className="flex flex-1 flex-col">
                        <span className="truncate">{opt.label}</span>
                        {opt.description ? (
                          <span className="truncate text-xs text-muted-foreground" title={opt.description}>
                            {opt.description}
                          </span>
                        ) : null}
                      </div>
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
