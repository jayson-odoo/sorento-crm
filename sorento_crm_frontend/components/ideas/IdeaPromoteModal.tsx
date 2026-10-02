'use client';

import { useEffect, useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useIdeaMutations } from '@/hooks/useIdeas';
import type { Idea } from '@/types/ideas';

/**
 * Promote to a Business Requirement: ss takes a title (and the idea). A refusal, such as the
 * user having no Business Requirements access over there, comes back as a toast and the modal
 * stays open.
 */
export function IdeaPromoteModal({
  idea,
  open,
  onOpenChange,
}: {
  idea: Idea;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { promote } = useIdeaMutations();
  const [title, setTitle] = useState('');

  useEffect(() => {
    if (open) setTitle(idea.title ?? idea.problem);
  }, [open, idea.title, idea.problem]);

  const canSave = title.trim().length > 0 && !promote.isPending;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    try {
      await promote.mutateAsync({ id: idea.id, title: title.trim() });
      onOpenChange(false);
    } catch {
      // The hook toasted ss's reason; the modal stays open.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Promote to Business Requirement</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogBody className="flex flex-col gap-1.5">
            <Label htmlFor="idea-promote-title">Title</Label>
            <Input
              id="idea-promote-title"
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
            />
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary" disabled={!canSave}>
              {promote.isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
              Promote
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
