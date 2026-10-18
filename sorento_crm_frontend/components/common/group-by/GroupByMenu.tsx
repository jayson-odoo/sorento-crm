'use client';

import * as React from 'react';
import { Layers, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';

export interface GroupByOption {
  id: string;
  label: string;
}

export interface GroupByMenuProps {
  options: GroupByOption[];
  value: string[];
  defaultValue: string[];
  onChange: (next: string[]) => void;
  onExpandAll?: () => void;
  onCollapseAll?: () => void;
  className?: string;
}

/**
 * Odoo-style multi-level Group by: a click adds a dimension as the next level, a second click
 * removes it. The chip names the levels in order and its x goes back to the default.
 */
export function GroupByMenu({
  options,
  value,
  defaultValue,
  onChange,
  onExpandAll,
  onCollapseAll,
  className,
}: GroupByMenuProps) {
  const labelOf = (id: string) => options.find((option) => option.id === id)?.label ?? id;
  const isDefault = value.join('|') === defaultValue.join('|');

  function toggle(id: string) {
    onChange(value.includes(id) ? value.filter((entry) => entry !== id) : [...value, id]);
  }

  return (
    <div data-testid="group-by-bar" className={cn('flex flex-wrap items-center gap-1.5', className)}>
      <Badge
        data-testid="group-by-chip"
        variant="secondary"
        size="md"
        className="max-w-full min-w-0 gap-1 font-normal"
      >
        <span className="text-muted-foreground">{value.length ? 'Group by' : 'Group by:'}</span>{' '}
        <span className="truncate">{value.length ? value.map(labelOf).join(' > ') : 'none'}</span>
        {!isDefault && (
          <button
            type="button"
            data-testid="group-by-chip-clear"
            aria-label="Reset group by"
            className="ms-0.5 inline-flex shrink-0 text-muted-foreground hover:text-foreground"
            onClick={() => onChange([...defaultValue])}
          >
            <X className="size-3" aria-hidden />
          </button>
        )}
      </Badge>
      <span className="flex-1" />
      {onExpandAll && (
        <Button type="button" variant="outline" size="sm" data-testid="group-by-expand-all" onClick={onExpandAll}>
          Expand all
        </Button>
      )}
      {onCollapseAll && (
        <Button type="button" variant="outline" size="sm" data-testid="group-by-collapse-all" onClick={onCollapseAll}>
          Collapse all
        </Button>
      )}
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="outline" size="sm" data-testid="group-by-trigger">
            <Layers className="size-3.5" aria-hidden />
            Group by
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[200px]">
          <DropdownMenuLabel className="font-medium">Group by</DropdownMenuLabel>
          {options.map((option) => {
            const level = value.indexOf(option.id);
            return (
              <DropdownMenuCheckboxItem
                key={option.id}
                data-testid={`group-by-option-${option.id}`}
                checked={level >= 0}
                // Stays open so several levels can be picked in a row.
                onSelect={(event) => {
                  event.preventDefault();
                  toggle(option.id);
                }}
              >
                {option.label}
                {level >= 0 && (
                  <span
                    data-testid={`group-by-level-${option.id}`}
                    aria-hidden
                    className="ms-auto ps-3 text-xs font-semibold text-primary"
                  >
                    {level + 1}
                  </span>
                )}
              </DropdownMenuCheckboxItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
