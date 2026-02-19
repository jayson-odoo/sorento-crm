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

interface SupplierOption {
  id: string;
  supplier_code: string;
  supplier_name: string;
}

interface SupplierComboboxProps {
  value: string;
  onChange: (value: string) => void;
  suppliers: SupplierOption[];
  supplierFallback?: { id: string; supplier_code: string; supplier_name: string } | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function SupplierCombobox({
  value,
  onChange,
  suppliers = [],
  supplierFallback,
  placeholder = 'Select supplier',
  disabled,
  className,
}: SupplierComboboxProps) {
  const [open, setOpen] = useState(false);
  const effectiveValue = value || null;
  const selected = suppliers.find((s) => s.id === effectiveValue) ?? (effectiveValue ? supplierFallback : null);
  const displayLabel = selected
    ? `${selected.supplier_name} (${selected.supplier_code})`
    : '';

  const options: SupplierOption[] = [
    ...suppliers,
    ...(supplierFallback && effectiveValue && !suppliers.some((s) => s.id === supplierFallback.id) ? [supplierFallback] : []),
  ];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          mode="input"
          placeholder={!effectiveValue}
          aria-expanded={open}
          disabled={disabled}
          className={cn('w-full justify-between', className)}
        >
          <span className={cn('truncate', !displayLabel && 'text-muted-foreground')}>
            {displayLabel || 'None'}
          </span>
          <ButtonArrow />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popper-anchor-width) p-0">
        <Command>
          <CommandInput placeholder={placeholder} />
          <CommandList>
            <ScrollArea viewportClassName="max-h-[300px] [&>div]:block!">
              <CommandEmpty>No supplier found.</CommandEmpty>
              <CommandGroup>
                <CommandItem
                  value="__none__"
                  onSelect={() => {
                    onChange('');
                    setOpen(false);
                  }}
                >
                  <span>None</span>
                  {!effectiveValue && <Check className="size-4 ms-auto" />}
                </CommandItem>
                {options.map((s) => (
                  <CommandItem
                    key={s.id}
                    value={`${s.supplier_code} ${s.supplier_name}`}
                    onSelect={() => {
                      onChange(value === s.id ? '' : s.id);
                      setOpen(false);
                    }}
                  >
                    <span className="truncate">
                      {s.supplier_name} ({s.supplier_code})
                    </span>
                    {effectiveValue === s.id && <Check className="size-4 ms-auto" />}
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
