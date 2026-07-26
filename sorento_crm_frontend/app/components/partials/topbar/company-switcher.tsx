'use client';

import { Building2, Check, ChevronDown } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useCompany } from '@/app/providers/CompanyProvider';

/**
 * Top-right active-company switcher. PLAN §11 - one active company at a time;
 * superadmin/multi-grant users see the full switchable list. Single-grant users
 * still see which company they are in, but as a read-only badge (nothing to
 * switch to). Zero grants / still loading renders nothing.
 */
export function CompanySwitcher() {
  const { grants, activeCompany, setActiveCompany } = useCompany();

  // activeCompany is null only while loading or with zero grants.
  if (!activeCompany) return null;

  // One grant: informational only. Same visual shell as the switcher (so the
  // header doesn't shift between user types) minus the chevron and the menu.
  if (grants.length <= 1) {
    return (
      <div
        className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm font-medium text-accent-foreground"
        title={`Active company: ${activeCompany.name}`}
        data-testid="company-indicator"
      >
        <Building2 className="size-4 shrink-0 text-muted-foreground" />
        <span className="truncate max-w-[120px] text-sm font-medium">
          {activeCompany.name}
        </span>
        <Badge variant="secondary" size="sm" className="font-mono shrink-0">
          {activeCompany.code}
        </Badge>
      </div>
    );
  }

  // setActiveCompany persists + re-mints the token and owns the success/error toast.
  const handleSelect = (companyId: string) => {
    if (companyId === activeCompany.id) return;
    setActiveCompany(companyId);
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          className="h-9 gap-2 px-3"
          title="Switch active company"
        >
          <Building2 className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate max-w-[120px]">{activeCompany.name}</span>
          <Badge variant="secondary" size="sm" className="font-mono shrink-0">
            {activeCompany.code}
          </Badge>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-[260px]" side="bottom" align="end">
        <DropdownMenuLabel>Active company</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {grants.map((company) => {
          const isActive = company.id === activeCompany.id;
          return (
            <DropdownMenuItem
              key={company.id}
              onClick={() => handleSelect(company.id)}
              className="flex items-center gap-3"
            >
              <div className="flex items-center justify-center shrink-0 rounded-lg bg-accent/60 border border-border size-9">
                <Building2 className="size-4 text-muted-foreground" />
              </div>
              <div className="flex flex-col min-w-0 flex-1">
                <span className="text-sm font-medium truncate">{company.name}</span>
                <span className="text-xs text-muted-foreground truncate">{company.code}</span>
              </div>
              <Check
                className={cn('size-4 shrink-0 text-primary', !isActive && 'opacity-0')}
              />
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
