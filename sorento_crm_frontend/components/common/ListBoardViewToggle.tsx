'use client';

import { LayoutGrid, LayoutList } from 'lucide-react';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { cn } from '@/lib/utils';
import type { ListBoardViewMode } from '@/hooks/useListBoardViewPreference';

export function ListBoardViewToggle({
  value,
  onChange,
  className,
}: {
  value: ListBoardViewMode;
  onChange: (mode: ListBoardViewMode) => void;
  className?: string;
}) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={value}
      onValueChange={(v) => {
        if (v === 'list' || v === 'board') onChange(v);
      }}
      className={cn('rounded-lg border border-input bg-muted/30 p-0.5 shadow-none', className)}
      aria-label="View mode"
    >
      <ToggleGroupItem value="list" aria-label="List view" className="size-9 rounded-md px-0 data-[state=on]:bg-background">
        <LayoutList className="size-4" />
      </ToggleGroupItem>
      <ToggleGroupItem value="board" aria-label="Board view" className="size-9 rounded-md px-0 data-[state=on]:bg-background">
        <LayoutGrid className="size-4" />
      </ToggleGroupItem>
    </ToggleGroup>
  );
}
