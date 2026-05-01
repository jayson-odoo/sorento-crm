'use client';

import * as React from 'react';
import { Check, ChevronDown } from 'lucide-react';
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

export type SearchableMultiSelectOption = {
  value: string;
  label: string;
  /** Optional grouping header (renders one CommandGroup per distinct group). */
  group?: string;
  /** Free-text used by the fuzzy filter; falls back to label. */
  searchText?: string;
  /** Optional secondary line under the label. */
  description?: string;
  /** When set, render a small badge after the label (e.g. "owned by X"). */
  badgeText?: string;
};

export type SearchableMultiSelectProps = {
  value: string[];
  onChange: (value: string[]) => void;
  options: SearchableMultiSelectOption[];
  placeholder?: string;
  emptyMessage?: string;
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
  /** Format the trigger label given the current selection. Defaults to "{count} selected". */
  renderTriggerLabel?: (selected: SearchableMultiSelectOption[]) => React.ReactNode;
};

export function SearchableMultiSelect({
  value,
  onChange,
  options,
  placeholder = 'Select...',
  emptyMessage = 'No results found.',
  disabled = false,
  className,
  triggerClassName,
  renderTriggerLabel,
}: SearchableMultiSelectProps) {
  const [open, setOpen] = React.useState(false);
  const selectedSet = React.useMemo(() => new Set(value), [value]);
  const selectedOptions = React.useMemo(
    () => options.filter((o) => selectedSet.has(o.value)),
    [options, selectedSet],
  );

  const grouped = React.useMemo(() => {
    const map = new Map<string, SearchableMultiSelectOption[]>();
    for (const opt of options) {
      const key = opt.group ?? '';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(opt);
    }
    return Array.from(map.entries());
  }, [options]);

  const toggle = (v: string) => {
    if (selectedSet.has(v)) {
      onChange(value.filter((x) => x !== v));
    } else {
      onChange([...value, v]);
    }
  };

  const triggerLabel = renderTriggerLabel
    ? renderTriggerLabel(selectedOptions)
    : selectedOptions.length === 0
      ? placeholder
      : `${selectedOptions.length} selected`;

  return (
    <Popover open={open} onOpenChange={(o) => !disabled && setOpen(o)}>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            'flex h-10 w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none',
            'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]',
            'data-[state=open]:border-ring',
            disabled && 'cursor-not-allowed opacity-50',
            triggerClassName,
          )}
        >
          <span className={cn('truncate', selectedOptions.length === 0 && 'text-muted-foreground')}>
            {triggerLabel}
          </span>
          <ChevronDown className="size-4 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent className={cn('w-[--radix-popover-trigger-width] p-0', className)} align="start">
        <Command shouldFilter>
          <CommandInput placeholder="Search..." />
          <CommandList>
            <CommandEmpty>{emptyMessage}</CommandEmpty>
            {grouped.map(([groupKey, opts]) => (
              <CommandGroup key={groupKey || '__ungrouped__'} heading={groupKey || undefined}>
                {opts.map((opt) => {
                  const isSelected = selectedSet.has(opt.value);
                  return (
                    <CommandItem
                      key={opt.value}
                      value={opt.searchText ?? `${opt.label} ${opt.description ?? ''}`}
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
