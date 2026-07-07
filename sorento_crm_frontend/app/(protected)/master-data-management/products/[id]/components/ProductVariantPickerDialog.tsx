'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Check, ChevronsUpDown, LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { getProductsForVariantSelect } from '../../services/productService';
import type { ProductVariantRef } from '../../types/product.types';

export interface ProductVariantPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  /** Label for the confirm button (e.g. "Set parent", "Add variant"). */
  confirmLabel: string;
  /** Product ids to hide from the picker (the current product + existing children). */
  excludeIds?: string[];
  submitting?: boolean;
  /** Called with the chosen product's id. */
  onConfirm: (productId: string) => void;
}

function displayProduct(p: ProductVariantRef): string {
  return `${p.product_code} — ${p.product_name}`;
}

/**
 * Shared product search combobox for variant curation (set/change parent + add
 * child). Resolves to a human-readable `code — name` label — never a raw UUID.
 */
export default function ProductVariantPickerDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  excludeIds = [],
  submitting = false,
  onConfirm,
}: ProductVariantPickerDialogProps) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<ProductVariantRef | null>(null);

  useEffect(() => {
    if (!open) {
      setSelected(null);
      setSearch('');
      setPickerOpen(false);
    }
  }, [open]);

  const { data: products = [], isLoading } = useQuery({
    queryKey: ['products-variant-select', search],
    queryFn: () => getProductsForVariantSelect(search || undefined),
    enabled: open,
    staleTime: 1000 * 30,
  });

  const excludeSet = useMemo(() => new Set(excludeIds), [excludeIds]);
  const options = useMemo(
    () => products.filter((p) => !excludeSet.has(p.id)),
    [products, excludeSet],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-1">
          <Label>Product</Label>
          <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                role="combobox"
                aria-expanded={pickerOpen}
                className="w-full justify-between font-normal"
                disabled={submitting}
              >
                <span className="truncate">
                  {selected ? displayProduct(selected) : 'Select a product'}
                </span>
                <ChevronsUpDown className="ms-2 size-4 shrink-0 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent
              className="w-[--radix-popover-trigger-width] p-0"
              align="start"
            >
              <Command shouldFilter={false}>
                <CommandInput
                  placeholder="Search by code or name..."
                  value={search}
                  onValueChange={setSearch}
                />
                <CommandList>
                  <CommandEmpty>
                    {isLoading ? 'Loading products…' : 'No products found.'}
                  </CommandEmpty>
                  <CommandGroup>
                    {options.map((p) => (
                      <CommandItem
                        key={p.id}
                        value={p.id}
                        onSelect={() => {
                          setSelected(p);
                          setPickerOpen(false);
                        }}
                      >
                        <Check
                          className={cn(
                            'me-2 size-4 shrink-0',
                            selected?.id === p.id ? 'opacity-100' : 'opacity-0',
                          )}
                        />
                        <span className="truncate">{displayProduct(p)}</span>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button
            onClick={() => selected && onConfirm(selected.id)}
            disabled={!selected || submitting}
          >
            {submitting && <LoaderCircleIcon className="animate-spin me-2 size-4" />}
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
