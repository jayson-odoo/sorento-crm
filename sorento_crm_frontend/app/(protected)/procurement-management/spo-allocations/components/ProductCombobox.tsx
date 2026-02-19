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

interface ProductOption {
  id: string;
  product_code: string;
  product_name?: string;
}

interface ProductComboboxProps {
  value: string;
  onChange: (value: string) => void;
  products: ProductOption[];
  productFallback?: { id: string; product_code: string; product_name?: string } | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function ProductCombobox({
  value,
  onChange,
  products = [],
  productFallback,
  placeholder = 'Select product',
  disabled,
  className,
}: ProductComboboxProps) {
  const [open, setOpen] = useState(false);
  const selected = products.find((p) => p.id === value) ?? (value ? productFallback : null);
  const displayLabel = selected
    ? `${selected.product_code}${selected.product_name && selected.product_name !== selected.product_code ? ` - ${selected.product_name}` : ''}`
    : '';

  const options: ProductOption[] = [
    ...products,
    ...(productFallback && value && !products.some((p) => p.id === productFallback.id) ? [productFallback] : []),
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
              <CommandEmpty>No product found.</CommandEmpty>
              <CommandGroup>
                {options.map((p) => (
                  <CommandItem
                    key={p.id}
                    value={`${p.product_code} ${p.product_name ?? ''}`}
                    onSelect={() => {
                      onChange(value === p.id ? '' : p.id);
                      setOpen(false);
                    }}
                  >
                    <span className="truncate">
                      {p.product_code} {p.product_name ? `- ${p.product_name}` : ''}
                    </span>
                    {value === p.id && <Check className="size-4 ms-auto" />}
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
