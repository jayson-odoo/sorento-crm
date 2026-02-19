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
import type { ProductCategory } from '../../products/types/product.types';

interface CategoryComboboxProps {
  value: string;
  onChange: (value: string) => void;
  categories: ProductCategory[] | undefined;
  productCategory?: { id: string; category_code: string; category_name?: string } | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function CategoryCombobox({
  value,
  onChange,
  categories = [],
  productCategory,
  placeholder = 'Search category...',
  disabled,
  className,
}: CategoryComboboxProps) {
  const [open, setOpen] = useState(false);
  const selectedCategory = categories.find((c) => c.id === value) ?? productCategory;
  const displayLabel = selectedCategory?.category_code ?? selectedCategory?.category_name ?? '';

  const options = [
    ...categories,
    ...(productCategory && !categories.some((c) => c.id === productCategory.id) ? [productCategory as ProductCategory] : []),
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
              <CommandEmpty>No category found.</CommandEmpty>
              <CommandGroup>
                {options.map((cat) => (
                  <CommandItem
                    key={cat.id}
                    value={`${cat.category_code} ${'category_name' in cat ? cat.category_name : ''}`}
                    onSelect={() => {
                      onChange(value === cat.id ? '' : cat.id);
                      setOpen(false);
                    }}
                  >
                    <span className="truncate">{cat.category_code}</span>
                    {value === cat.id && <Check className="size-4 ms-auto" />}
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
