'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Check, LoaderCircleIcon } from 'lucide-react';
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

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;

export interface ProductOption {
  id: string;
  product_code: string;
  product_name?: string;
}

export interface ProductComboboxSearchableProps {
  value: string;
  onChange: (value: string) => void;
  /** Fetch products from API: (searchQuery, pageIndex) => Promise<{ data: ProductOption[] }> */
  fetchProducts: (query: string, pageIndex: number) => Promise<{ data: ProductOption[] }>;
  productFallback?: ProductOption | null;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
}

export function ProductComboboxSearchable({
  value,
  onChange,
  fetchProducts,
  productFallback,
  placeholder = 'Search or select product',
  disabled,
  className,
}: ProductComboboxSearchableProps) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<ProductOption[]>([]);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastLoadedQueryRef = useRef<string | null>(null);

  const selected =
    options.find((p) => p.id === value) ??
    (value && productFallback ? productFallback : null);
  const displayLabel = selected
    ? `${selected.product_code}${selected.product_name && selected.product_name !== selected.product_code ? ` - ${selected.product_name}` : ''}`
    : '';

  const loadPage = useCallback(
    async (query: string, pageIndex: number, append: boolean) => {
      if (append) setLoadingMore(true);
      else setLoading(true);
      try {
        const res = await fetchProducts(query, pageIndex);
        const data = res.data ?? [];
        setOptions((prev) => (append ? [...prev, ...data] : data));
        setHasMore(data.length >= PAGE_SIZE);
      } catch {
        setOptions((prev) => (append ? prev : []));
        setHasMore(false);
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [fetchProducts],
  );

  // When popover opens, load first page and reset state
  useEffect(() => {
    if (open) {
      setSearch('');
      setSearchInput('');
      setPage(0);
      lastLoadedQueryRef.current = '';
      loadPage('', 0, false);
    }
  }, [open, loadPage]);

  // Debounced search: when searchInput changes, fetch after delay
  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const query = searchInput.trim();
      if (query === lastLoadedQueryRef.current) {
        debounceRef.current = null;
        return;
      }
      lastLoadedQueryRef.current = query;
      setSearch(query);
      setPage(0);
      loadPage(query, 0, false);
      debounceRef.current = null;
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [open, searchInput, loadPage]);

  const handleLoadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    loadPage(search.trim(), nextPage, true);
  };

  const displayOptions: ProductOption[] = [
    ...(productFallback && value && !options.some((p) => p.id === productFallback.id) ? [productFallback] : []),
    ...options,
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
        <Command
          shouldFilter={false}
          onValueChange={() => {}}
        >
          <CommandInput
            placeholder="Type to search..."
            value={searchInput}
            onValueChange={setSearchInput}
          />
          <CommandList>
            <ScrollArea viewportClassName="max-h-[300px] [&>div]:block!">
              {loading ? (
                <div className="flex items-center justify-center py-6 text-muted-foreground">
                  <LoaderCircleIcon className="size-6 animate-spin" />
                </div>
              ) : (
                <>
                  <CommandEmpty>No product found. Try a different search.</CommandEmpty>
                  <CommandGroup>
                    {displayOptions.map((p) => (
                      <CommandItem
                        key={p.id}
                        value={p.id}
                        onSelect={() => {
                          onChange(p.id);
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
                  {!loading && hasMore && displayOptions.length > 0 && (
                    <div className="border-t p-2 text-center">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="w-full"
                        onClick={handleLoadMore}
                        disabled={loadingMore}
                      >
                        {loadingMore ? (
                          <LoaderCircleIcon className="size-4 animate-spin" />
                        ) : (
                          'Load more'
                        )}
                      </Button>
                    </div>
                  )}
                </>
              )}
            </ScrollArea>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
