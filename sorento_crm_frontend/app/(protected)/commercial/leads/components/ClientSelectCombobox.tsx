'use client';

import { useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button, ButtonArrow } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { getCustomers } from '@/app/(protected)/order-management/customers/services/customerService';
import type { Customer } from '@/app/(protected)/order-management/customers/types/customer.types';

type Props = {
  value: string;
  onChange: (customerId: string) => void;
  selectedCustomer?: Customer | null;
  disabled?: boolean;
  className?: string;
  /** Placeholder when no client is selected (trigger label). */
  emptyLabel?: string;
  /** Called when search has no results; opens full create-client flow with `searchQuery` prefilled. */
  onCreateNew?: (searchQuery: string) => void;
};

export function ClientSelectCombobox({
  value,
  onChange,
  selectedCustomer,
  disabled,
  className,
  emptyLabel = 'Search client…',
  onCreateNew,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [options, setOptions] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(false);
  const queryTrimmed = query.trim().toLowerCase();

  useEffect(() => {
    let cancelled = false;
    const t = window.setTimeout(() => {
      setLoading(true);
      getCustomers({
        pageIndex: 0,
        pageSize: 50,
        sorting: [{ id: 'customer_name', desc: false }],
        searchQuery: query.trim(),
        status: 'active',
      })
        .then((res) => {
          if (!cancelled) setOptions(res.data);
        })
        .catch(() => {
          if (!cancelled) setOptions([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [query, open]);

  const merged = [...options];
  // Keep selected item visible only when not actively searching,
  // so search results are not polluted by prior selection.
  if (!queryTrimmed && selectedCustomer && !merged.some((c) => c.id === selectedCustomer.id)) {
    merged.unshift(selectedCustomer);
  }
  // Guard against backend fuzzy/irrelevant results by applying a strict client-side match.
  const visibleOptions = queryTrimmed
    ? merged.filter((c) => {
        const hay = `${c.customer_name || ''} ${c.customer_code || ''}`.toLowerCase();
        return hay.includes(queryTrimmed);
      })
    : merged;

  const selected = merged.find((c) => c.id === value);
  const label = selected ? `${selected.customer_name} (${selected.customer_code})` : '';

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          mode="input"
          placeholder={!value}
          aria-expanded={open}
          disabled={disabled}
          className={cn('w-full justify-between', className)}
        >
          <span className={cn('truncate', !label && 'text-muted-foreground')}>
            {label || emptyLabel}
          </span>
          <ButtonArrow />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popper-anchor-width) p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Search clients…" value={query} onValueChange={setQuery} />
          <CommandList>
            <ScrollArea viewportClassName="max-h-[280px] [&>div]:block!">
              <CommandEmpty>
                {loading ? (
                  'Loading…'
                ) : (
                  <div className="flex flex-col items-stretch gap-3 py-2">
                    <p className="text-muted-foreground text-center text-sm">No client found.</p>
                    {onCreateNew && query.trim().length > 0 ? (
                      <Button
                        type="button"
                        variant="outline"
                        className="w-full border-[#e7000b] text-[#e7000b] hover:bg-[#fef2f2]"
                        onClick={() => {
                          onCreateNew(query.trim());
                          setOpen(false);
                        }}
                      >
                        Create new client
                      </Button>
                    ) : null}
                  </div>
                )}
              </CommandEmpty>
              <CommandGroup>
                {visibleOptions.map((c) => (
                  <CommandItem
                    key={c.id}
                    value={`${c.customer_code} ${c.customer_name}`}
                    onSelect={() => {
                      onChange(c.id);
                      setOpen(false);
                    }}
                  >
                    <span className="truncate">
                      {c.customer_name}{' '}
                      <span className="text-muted-foreground">({c.customer_code})</span>
                    </span>
                    {value === c.id && <Check className="size-4 ms-auto shrink-0" />}
                  </CommandItem>
                ))}
              </CommandGroup>
            </ScrollArea>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
