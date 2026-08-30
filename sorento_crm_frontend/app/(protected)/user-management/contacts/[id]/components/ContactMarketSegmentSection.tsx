'use client';

import { useEffect, useMemo, useState } from 'react';
import { Pencil } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  useContactMarketSegments,
  useMarketSegments,
  useSetContactMarketSegments,
} from '@/app/(protected)/user-management/market-segments/hooks/useMarketSegments';

/**
 * Contact Details → Market Segment section. A contact's segments (retail /
 * project) route inbound conversations to CS members serving that segment. An
 * untagged contact matches ALL CS members, so the empty state says as much.
 * Unassigning a segment is a destructive/detach action → confirmed first (B4).
 */
export default function ContactMarketSegmentSection({ contactId }: { contactId: string }) {
  const { data: assigned = [], isLoading: assignedLoading } = useContactMarketSegments(contactId);
  const { data: catalog = [], isLoading: catalogLoading } = useMarketSegments(true);
  const setSegments = useSetContactMarketSegments(contactId);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [draft, setDraft] = useState<string[]>([]);

  useEffect(() => {
    if (dialogOpen) setDraft(assigned);
  }, [dialogOpen, assigned]);

  const nameByCode = useMemo(() => {
    const m = new Map<string, string>();
    catalog.forEach((s) => m.set(s.code, s.name));
    return m;
  }, [catalog]);

  const label = (code: string) => nameByCode.get(code) ?? code;

  const removed = useMemo(
    () => assigned.filter((c) => !draft.includes(c)),
    [assigned, draft],
  );

  function toggle(code: string, checked: boolean) {
    setDraft((prev) => {
      const next = new Set(prev);
      if (checked) next.add(code);
      else next.delete(code);
      return Array.from(next);
    });
  }

  function persist() {
    setSegments.mutate(draft, {
      onSuccess: () => {
        setConfirmOpen(false);
        setDialogOpen(false);
      },
    });
  }

  function onSave() {
    if (removed.length > 0) {
      setConfirmOpen(true);
      return;
    }
    persist();
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <p className="text-sm text-muted-foreground">Market segment</p>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setDialogOpen(true)}
          className="h-6 w-6 p-0"
          aria-label="Edit market segment"
        >
          <Pencil className="h-3 w-3" />
        </Button>
      </div>

      {assignedLoading || catalogLoading ? (
        <Skeleton className="h-6 w-40" />
      ) : assigned.length > 0 ? (
        <div className="flex flex-wrap gap-1 mt-1">
          {assigned.map((code) => (
            <Badge key={code} variant="secondary" className="font-normal">
              {label(code)}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="font-medium text-muted-foreground">No market segment - matches all CS members</p>
      )}

      {/* Edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit market segment</DialogTitle>
          </DialogHeader>
          <div className="flex flex-wrap gap-3 py-2">
            {catalog.length === 0 ? (
              <span className="text-xs text-muted-foreground">
                No market segments configured. Add some under User Management → Market Segments.
              </span>
            ) : (
              catalog.map((opt) => {
                const id = `contact-segment-${opt.code}`;
                return (
                  <label
                    key={opt.code}
                    htmlFor={id}
                    className="flex items-center gap-2 text-sm border rounded-md px-2 py-1 cursor-pointer hover:bg-accent"
                  >
                    <Checkbox
                      id={id}
                      checked={draft.includes(opt.code)}
                      onCheckedChange={(v) => toggle(opt.code, v === true)}
                      disabled={setSegments.isPending}
                    />
                    <span>{opt.name}</span>
                  </label>
                );
              })
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Leave empty to match all CS members (no segment routing).
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={onSave} disabled={setSegments.isPending}>
              Save segments
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirm unassign (destructive-action rule) */}
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm changes</AlertDialogTitle>
            <AlertDialogDescription>
              This will unassign {removed.map(label).join(', ')} from this contact. This action cannot
              be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={setSegments.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                persist();
              }}
              disabled={setSegments.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Unassign segments
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
