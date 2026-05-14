'use client';

import { useState } from 'react';
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';

interface PackingListOption {
  id: string;
  shipment_number: string | null;
  shipping_container_number?: string | null;
}

interface PackingListComboboxProps {
  value: string;
  onChange: (value: string) => void;
  packingLists: PackingListOption[];
  packingListFallback?: { id: string; shipment_number: string | null; shipping_container_number?: string | null } | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function PackingListCombobox({
  value,
  onChange,
  packingLists = [],
  packingListFallback,
  placeholder = 'Select packing list',
  disabled,
  className,
}: PackingListComboboxProps) {
  const [open, setOpen] = useState(false);
  const selected = packingLists.find((pl) => pl.id === value) ?? (value ? packingListFallback : null);
  const displayLabel = selected
    ? selected.shipping_container_number ?? selected.shipment_number ?? selected.id
    : '';

  const options: PackingListOption[] = [
    ...packingLists,
    ...(packingListFallback && value && !packingLists.some((pl) => pl.id === packingListFallback.id) ? [packingListFallback] : []),
  ];

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
          <span className={cn('truncate', !displayLabel && 'text-muted-foreground')}>
            {displayLabel || placeholder}
          </span>
          <ButtonArrow />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popper-anchor-width) p-0">
        <Command>
          <CommandInput placeholder={placeholder} />
          <CommandList>
            <ScrollArea viewportClassName="max-h-[300px] [&>div]:block!">
              <CommandEmpty>No packing list found.</CommandEmpty>
              <CommandGroup>
                {options.map((pl) => (
                  <CommandItem
                    key={pl.id}
                    value={`${pl.shipment_number ?? ''} ${pl.shipping_container_number ?? ''}`}
                    onSelect={() => {
                      onChange(value === pl.id ? '' : pl.id);
                      setOpen(false);
                    }}
                  >
                    <span className="truncate">
                      {pl.shipping_container_number ?? pl.shipment_number ?? pl.id}
                    </span>
                    {value === pl.id && <Check className="size-4 ms-auto" />}
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
