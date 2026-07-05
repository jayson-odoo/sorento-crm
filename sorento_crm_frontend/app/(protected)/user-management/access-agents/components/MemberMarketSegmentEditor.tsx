'use client';

import { useEffect, useMemo, useState } from 'react';
import { Tag } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  useMarketSegments,
  useMemberMarketSegments,
  useSetMemberMarketSegments,
} from '@/app/(protected)/user-management/market-segments/hooks/useMarketSegments';

/**
 * Per-member market-segment multiselect within a CS team roster. A member's
 * segments (retail / project) restrict which contacts route to them; both =
 * both checked. A member with no segments serves ALL contacts ("Serves all").
 * Keyed by (team_id, user_id) so the same person can serve different segments
 * across teams. See PLAN-cs-team-market-segment-routing.md.
 */
export default function MemberMarketSegmentEditor({
  teamId,
  userId,
}: {
  teamId: string;
  userId: string;
}) {
  const { data: assigned = [], isLoading } = useMemberMarketSegments(teamId, userId);
  const { data: catalog = [] } = useMarketSegments(true);
  const setSegments = useSetMemberMarketSegments(teamId, userId);

  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string[]>([]);

  useEffect(() => {
    if (open) setDraft(assigned);
  }, [open, assigned]);

  const nameByCode = useMemo(() => {
    const m = new Map<string, string>();
    catalog.forEach((s) => m.set(s.code, s.name));
    return m;
  }, [catalog]);

  const label = (code: string) => nameByCode.get(code) ?? code;

  function toggle(code: string, checked: boolean) {
    setDraft((prev) => {
      const next = new Set(prev);
      if (checked) next.add(code);
      else next.delete(code);
      return Array.from(next);
    });
  }

  function save() {
    setSegments.mutate(draft, { onSuccess: () => setOpen(false) });
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
          aria-label="Edit market segments"
        >
          <Tag className="size-3" aria-hidden />
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
            <span>Serves all</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64">
        <div className="space-y-3">
          <p className="text-xs font-medium text-muted-foreground">Market segments served</p>
          {catalog.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No market segments configured. Add some under User Management → Market Segments.
            </p>
          ) : (
            <div className="space-y-2">
              {catalog.map((opt) => {
                const id = `member-segment-${teamId}-${userId}-${opt.code}`;
                return (
                  <label key={opt.code} htmlFor={id} className="flex items-center gap-2 text-sm cursor-pointer">
                    <Checkbox
                      id={id}
                      checked={draft.includes(opt.code)}
                      onCheckedChange={(v) => toggle(opt.code, v === true)}
                      disabled={setSegments.isPending}
                    />
                    <span>{opt.name}</span>
                  </label>
                );
              })}
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            Leave empty to serve all contacts.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setOpen(false)} disabled={setSegments.isPending}>
              Cancel
            </Button>
            <Button size="sm" onClick={save} disabled={setSegments.isPending || catalog.length === 0}>
              Save
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
