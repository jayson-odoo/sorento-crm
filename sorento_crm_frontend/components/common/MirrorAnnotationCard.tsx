'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Save } from 'lucide-react';

/**
 * The ONE thing a user may change on an AutoCount mirror record: a Sorento-only
 * note + follow-up flag. Ingest never writes these columns, so they survive
 * re-sync. Shared across every mirror detail page so the editor cannot drift.
 *
 * Built entirely from existing system primitives (Card / Textarea / Switch /
 * Button / Label) to keep one design language — no bespoke widget.
 */
export interface MirrorAnnotation {
  internal_note?: string | null;
  follow_up?: boolean;
}

export function MirrorAnnotationCard({
  value,
  onSave,
  isSaving = false,
}: {
  value: MirrorAnnotation;
  onSave: (next: { internal_note: string; follow_up: boolean }) => void;
  isSaving?: boolean;
}) {
  const [note, setNote] = useState(value.internal_note ?? '');
  const [followUp, setFollowUp] = useState(Boolean(value.follow_up));

  // Reconcile local state whenever the underlying record changes (e.g. refetch).
  useEffect(() => {
    setNote(value.internal_note ?? '');
    setFollowUp(Boolean(value.follow_up));
  }, [value.internal_note, value.follow_up]);

  const dirty = note !== (value.internal_note ?? '') || followUp !== Boolean(value.follow_up);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Internal notes</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="mirror-internal-note">Note</Label>
          <Textarea
            id="mirror-internal-note"
            placeholder="Add an internal note (Sorento-only, kept across syncs)…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={4}
          />
        </div>
        <div className="flex items-center gap-3">
          <Switch id="mirror-follow-up" checked={followUp} onCheckedChange={setFollowUp} />
          <Label htmlFor="mirror-follow-up" className="cursor-pointer">
            Flag for follow-up
          </Label>
        </div>
        <div className="flex justify-end">
          <Button
            onClick={() => onSave({ internal_note: note, follow_up: followUp })}
            disabled={!dirty || isSaving}
          >
            <Save className="size-4" />
            {isSaving ? 'Saving…' : 'Save note'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
