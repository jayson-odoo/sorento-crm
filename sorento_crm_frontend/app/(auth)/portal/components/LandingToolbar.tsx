'use client';

/**
 * Landing toolbar row (D-L3): Filter, Sort, view toggle on the left, "New
 * <type>" on the right (rendered by the caller - SubmissionList already has
 * the Link + label for it). Filter and Sort share one field descriptor table
 * (landing-fields.ts) so they never offer different fields for the same kind.
 */
import { ArrowDownUp, Filter as FilterIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
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
          <DropdownMenuRadioGroup
            value={`${sort.key}:${sort.dir}`}
            onValueChange={(v) => {
              const idx = v.lastIndexOf(':');
              const key = v.slice(0, idx);
              const dir = v.slice(idx + 1) as 'asc' | 'desc';
              onSortChange({ key, dir });
            }}
          >
            {fields.map((field, idx) => (
              <div key={field.key}>
                {idx > 0 && <DropdownMenuSeparator />}
                <DropdownMenuLabel>{field.label}</DropdownMenuLabel>
                <DropdownMenuRadioItem value={`${field.key}:asc`}>
                  Ascending
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value={`${field.key}:desc`}>
                  Descending
                </DropdownMenuRadioItem>
              </div>
            ))}
          </DropdownMenuRadioGroup>
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
        <div className="flex items-center gap-2">
          <Input
            type="date"
            aria-label={`${field.label} from`}
            value={range.from ?? ''}
            onChange={(e) =>
              onChange({ ...range, from: e.target.value || undefined })
            }
            className="h-9"
          />
          <span className="text-xs text-muted-foreground">to</span>
          <Input
            type="date"
            aria-label={`${field.label} to`}
            value={range.to ?? ''}
            onChange={(e) =>
              onChange({ ...range, to: e.target.value || undefined })
            }
            className="h-9"
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
