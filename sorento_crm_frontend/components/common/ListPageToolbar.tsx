'use client';

import { Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

export interface ListPageToolbarProps {
  searchPlaceholder?: string;
  searchValue?: string;
  onSearchChange?: (value: string) => void;
  /** Called on Enter; use to e.g. reset pagination */
  onSearchSubmit?: () => void;
  createButton: React.ReactNode;
  /**
   * Accepted for API compatibility but intentionally NOT applied to the search
   * input - disabling the field on each query causes focus loss while typing.
   * Gate your create/columns buttons on their own loading state instead.
   */
  isLoading?: boolean;
  /** Hide search input when true (e.g. for small lists) */
  hideSearch?: boolean;
}

/**
 * Standard list page toolbar: search input + create button.
 * Use in CardHeader for DataGrid-backed list pages.
 */
export function ListPageToolbar({
  searchPlaceholder = 'Search...',
  searchValue = '',
  onSearchChange,
  onSearchSubmit,
  createButton,
  // `isLoading` is intentionally not destructured/used here (see prop doc).
  hideSearch = false,
}: ListPageToolbarProps) {
  return (
    <CardHeader className="flex-row items-center justify-between py-5">
      {!hideSearch && (
        <div className="relative">
          <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
          {/*
            Do NOT disable the search input while loading. Each keystroke
            updates a query whose key includes the search term, so the query
            briefly enters its pending state (isLoading=true). Disabling the
            input on that flip makes the browser blur the (now disabled) field,
            losing focus after every character. Keep the field always
            interactive so typing is continuous; the create/columns buttons in
            `createButton` gate themselves on their own loading state.
          */}
          <Input
            placeholder={searchPlaceholder}
            value={searchValue}
            onChange={(e) => onSearchChange?.(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (onSearchSubmit?.(), e.preventDefault())}
            className="ps-9 w-full md:w-64"
          />
          {searchValue && (
            <Button
              mode="icon"
              variant="dim"
              type="button"
              className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
              onClick={() => onSearchChange?.('')}
            >
              <X />
            </Button>
          )}
        </div>
      )}
      <div className={cn('flex items-center gap-3', hideSearch && 'ms-auto')}>
        {createButton}
      </div>
    </CardHeader>
  );
}
