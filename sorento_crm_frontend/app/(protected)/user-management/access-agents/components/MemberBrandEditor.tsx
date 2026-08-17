'use client';

import { useEffect, useMemo, useState } from 'react';
import { Bookmark } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
import { useMemberBrands, useSetMemberBrands } from '../hooks/useMemberBrands';

/**
 * Per-member brand multiselect within a team roster. A member's brands restrict
 * which work routes to them; a member with no brands serves ALL brands ("All
 * brands"). When nobody in the team carries the brand asked for, the whole team
 * round-robins. Keyed by (team_id, user_id) so the same person can serve
 * different brands across teams. Mirrors MemberMarketSegmentEditor.
 */
export default function MemberBrandEditor({
  teamId,
  userId,
}: {
  teamId: string;
  userId: string;
}) {
  const { data: assigned = [], isLoading } = useMemberBrands(teamId, userId);
  const { data: catalog = [] } = useBrandSelectQuery();
  const setBrands = useSetMemberBrands(teamId, userId);

  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string[]>([]);

  useEffect(() => {
    if (open) setDraft(assigned);
  }, [open, assigned]);

  const options = useMemo(
    () =>
      catalog.map((b) => ({
        code: String(b.brand_code ?? '').toLowerCase(),
        name: b.brand_name,
      })),
    [catalog],
  );

  const nameByCode = useMemo(() => {
    const m = new Map<string, string>();
    options.forEach((o) => m.set(o.code, o.name));
    return m;
  }, [options]);

  const label = (code: string) => nameByCode.get(code) ?? code.toUpperCase();

  function toggle(code: string, checked: boolean) {
    setDraft((prev) => {
      const next = new Set(prev);
      if (checked) next.add(code);
      else next.delete(code);
      return Array.from(next);
    });
  }

  function save() {
    setBrands.mutate(draft, { onSuccess: () => setOpen(false) });
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
          aria-label="Edit brands"
        >
          <Bookmark className="size-3" aria-hidden />
          {isLoading ? (
            <span>…</span>
          ) : assigned.length > 0 ? (
            <span className="flex flex-wrap items-center gap-1">
              {assigned.map((code) => (
                <Badge key={code} variant="secondary" className="text-[10px] font-normal">
                  {label(code)}
                </Badge>
              ))}
            </span>
          ) : (
            <span>All brands</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64">
        <div className="space-y-3">
          <p className="text-xs font-medium text-muted-foreground">Brands served</p>
          {options.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No brands configured. Add some under Master Data → Brands.
            </p>
          ) : (
            <div className="max-h-56 space-y-2 overflow-y-auto">
              {options.map((opt) => {
                const id = `member-brand-${teamId}-${userId}-${opt.code}`;
                return (
                  <label key={opt.code} htmlFor={id} className="flex items-center gap-2 text-sm cursor-pointer">
                    <Checkbox
                      id={id}
                      checked={draft.includes(opt.code)}
                      onCheckedChange={(v) => toggle(opt.code, v === true)}
                      disabled={setBrands.isPending}
                    />
                    <span>{opt.name}</span>
                  </label>
                );
              })}
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Leave empty to serve all brands.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setOpen(false)} disabled={setBrands.isPending}>
              Cancel
            </Button>
            <Button size="sm" onClick={save} disabled={setBrands.isPending || options.length === 0}>
              Save
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
