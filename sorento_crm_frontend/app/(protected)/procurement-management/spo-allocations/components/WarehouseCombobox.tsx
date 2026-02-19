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

interface WarehouseOption {
  id: string;
  warehouse_code: string;
  warehouse_name: string;
}

interface WarehouseComboboxProps {
  value: string;
  onChange: (value: string) => void;
  warehouses: WarehouseOption[];
  warehouseFallback?: { id: string; warehouse_code: string; warehouse_name: string } | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function WarehouseCombobox({
  value,
  onChange,
  warehouses = [],
  warehouseFallback,
  placeholder = 'Select warehouse',
  disabled,
  className,
}: WarehouseComboboxProps) {
  const [open, setOpen] = useState(false);
  const selected = warehouses.find((w) => w.id === value) ?? (value ? warehouseFallback : null);
  const displayLabel = selected ? `${selected.warehouse_code} - ${selected.warehouse_name}` : '';

  const options: WarehouseOption[] = [
    ...warehouses,
    ...(warehouseFallback && value && !warehouses.some((w) => w.id === warehouseFallback.id) ? [warehouseFallback] : []),
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
              <CommandEmpty>No warehouse found.</CommandEmpty>
              <CommandGroup>
                {options.map((w) => (
                  <CommandItem
                    key={w.id}
                    value={`${w.warehouse_code} ${w.warehouse_name}`}
                    onSelect={() => {
                      onChange(value === w.id ? '' : w.id);
                      setOpen(false);
                    }}
                  >
                    <span className="truncate">
                      {w.warehouse_code} - {w.warehouse_name}
                    </span>
                    {value === w.id && <Check className="size-4 ms-auto" />}
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
