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
  isLoading = false,
  hideSearch = false,
}: ListPageToolbarProps) {
  return (
    <CardHeader className="flex-row items-center justify-between py-5">
      {!hideSearch && (
        <div className="relative">
          <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
          <Input
            placeholder={searchPlaceholder}
            value={searchValue}
            onChange={(e) => onSearchChange?.(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (onSearchSubmit?.(), e.preventDefault())}
            disabled={isLoading}
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
