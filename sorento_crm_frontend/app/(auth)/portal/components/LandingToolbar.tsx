'use client';

/**
 * Landing toolbar row (D-L3): Filter, Sort, view toggle on the left, "New
 * <type>" on the right (rendered by the caller - SubmissionList already has
 * the Link + label for it). Filter and Sort share one field descriptor table
 * (landing-fields.ts) so they never offer different fields for the same kind.
 */
import { ArrowDown, ArrowDownUp, ArrowUp, Filter as FilterIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { ListBoardViewToggle } from '@/components/common/ListBoardViewToggle';
import type { ListBoardViewMode } from '@/hooks/useListBoardViewPreference';
import {
  activeLandingFilterCount,
  landingFilterOptions,
  type LandingDateRange,
  type LandingField,
  type LandingFilters,
  type LandingSort,
} from '../lib/landing-fields';
import type { PortalSubmissionSummary } from '../lib/portal-client';

export function LandingToolbar({
  fields,
  items,
  filters,
  onFiltersChange,
  sort,
  onSortChange,
  view,
  onViewChange,
}: {
  fields: LandingField[];
  items: PortalSubmissionSummary[];
  filters: LandingFilters;
  onFiltersChange: (next: LandingFilters) => void;
  sort: LandingSort;
  onSortChange: (next: LandingSort) => void;
  view: ListBoardViewMode;
  onViewChange: (mode: ListBoardViewMode) => void;
}) {
  const activeCount = activeLandingFilterCount(filters);
  const sortField = fields.find((f) => f.key === sort.key) ?? fields[0];

  return (
    <div className="flex items-center gap-2">
      <Popover>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label="Filter"
            title="Filter"
          >
            <FilterIcon />
            {activeCount > 0 && (
              <Badge variant="secondary" className="px-1.5 py-0 text-xs">
                {activeCount}
              </Badge>
            )}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-80 space-y-3">
          {fields.map((field) => (
            <FilterField
              key={field.key}
              field={field}
              items={items}
              value={filters[field.key]}
              onChange={(next) => {
                const copy = { ...filters };
                if (
                  next === undefined ||
                  next === '' ||
                  (typeof next === 'object' && !next.from && !next.to)
                ) {
                  delete copy[field.key];
                } else {
                  copy[field.key] = next;
                }
                onFiltersChange(copy);
              }}
            />
          ))}
          <div className="flex justify-end pt-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onFiltersChange({})}
              disabled={activeCount === 0}
            >
              Clear all
            </Button>
          </div>
        </PopoverContent>
      </Popover>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-label="Sort"
            title="Sort"
          >
            <ArrowDownUp />
            {sortField && (
              <span className="hidden md:inline">{sortField.label}</span>
            )}
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="min-w-[12rem]">
          {/* R3-3: one row per field, not an Ascending/Descending pair - the
              active field shows its own direction as an arrow; tapping it
              flips that direction, tapping another field selects it at its
              type's natural default (dates newest first, text A to Z). */}
          {fields.map((field) => {
            const isActive = sort.key === field.key;
            return (
              <DropdownMenuItem
                key={field.key}
                onSelect={(e) => {
                  e.preventDefault();
                  onSortChange({
                    key: field.key,
                    dir: isActive
                      ? sort.dir === 'asc'
                        ? 'desc'
                        : 'asc'
                      : field.type === 'date'
                        ? 'desc'
                        : 'asc',
                  });
                }}
              >
                <span className="flex-1">{field.label}</span>
                {isActive &&
                  (sort.dir === 'asc' ? (
                    <ArrowUp className="size-3.5 text-muted-foreground" />
                  ) : (
                    <ArrowDown className="size-3.5 text-muted-foreground" />
                  ))}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>

      <ListBoardViewToggle value={view} onChange={onViewChange} />
    </div>
  );
}

function FilterField({
  field,
  items,
  value,
  onChange,
}: {
  field: LandingField;
  items: PortalSubmissionSummary[];
  value: LandingFilters[string] | undefined;
  onChange: (next: LandingFilters[string] | undefined) => void;
}) {
  if (field.type === 'date') {
    const range = (value as LandingDateRange | undefined) ?? {};
    return (
      <div className="space-y-1.5">
        <Label className="text-xs text-muted-foreground">{field.label}</Label>
        {/* R3-4: `min-w-0 flex-1` on both inputs - a native date input's
            intrinsic width otherwise pushed the row past the popover edge
            at 375px (and cramped it at 1280). */}
        <div className="flex items-center gap-2">
          <Input
            type="date"
            aria-label={`${field.label} from`}
            value={range.from ?? ''}
            onChange={(e) =>
              onChange({ ...range, from: e.target.value || undefined })
            }
            className="h-9 min-w-0 flex-1"
          />
          <span className="shrink-0 text-xs text-muted-foreground">to</span>
          <Input
            type="date"
            aria-label={`${field.label} to`}
            value={range.to ?? ''}
            onChange={(e) =>
              onChange({ ...range, to: e.target.value || undefined })
            }
            className="h-9 min-w-0 flex-1"
          />
        </div>
      </div>
    );
  }

  const options = landingFilterOptions(items, field).map((v) => ({
    value: v,
    label: v,
  }));

  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{field.label}</Label>
      <SearchableSelect
        value={(value as string | undefined) ?? ''}
        onChange={(v) => onChange(v || undefined)}
        options={options}
        clearable
        size="sm"
        placeholder={`Any ${field.label.toLowerCase()}`}
        emptyMessage="No values in this list."
      />
    </div>
  );
}
