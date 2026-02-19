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
import type { Brand } from '../../products/types/product.types';

interface BrandComboboxProps {
  value: string | null | undefined;
  onChange: (value: string | null) => void;
  brands: Brand[] | undefined;
  productBrand?: { id: string; brand_code: string; brand_name?: string } | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function BrandCombobox({
  value,
  onChange,
  brands = [],
  productBrand,
  placeholder = 'Search brand...',
  disabled,
  className,
}: BrandComboboxProps) {
  const [open, setOpen] = useState(false);
  const effectiveValue = value ?? null;
  const selectedBrand = brands.find((b) => b.id === effectiveValue) ?? (effectiveValue ? productBrand : null);
  const displayLabel = selectedBrand?.brand_code ?? selectedBrand?.brand_name ?? 'None';

  const options = [
    ...brands,
    ...(productBrand && effectiveValue && !brands.some((b) => b.id === productBrand.id) ? [productBrand as Brand] : []),
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
          <span className={cn('truncate', !effectiveValue && 'text-muted-foreground')}>
            {effectiveValue ? displayLabel : 'None'}
          </span>
          <ButtonArrow />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popper-anchor-width) p-0">
        <Command>
          <CommandInput placeholder={placeholder} />
          <CommandList>
            <ScrollArea viewportClassName="max-h-[300px] [&>div]:block!">
              <CommandEmpty>No brand found.</CommandEmpty>
              <CommandGroup>
                <CommandItem
                  value="__none__"
                  onSelect={() => {
                    onChange(null);
                    setOpen(false);
                  }}
                >
                  <span>None</span>
                  {!effectiveValue && <Check className="size-4 ms-auto" />}
                </CommandItem>
                {options.map((brand) => (
                  <CommandItem
                    key={brand.id}
                    value={`${brand.brand_code} ${'brand_name' in brand ? brand.brand_name : ''}`}
                    onSelect={() => {
                      onChange(value === brand.id ? null : brand.id);
                      setOpen(false);
                    }}
                  >
                    <span className="truncate">{brand.brand_code}</span>
                    {effectiveValue === brand.id && <Check className="size-4 ms-auto" />}
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
