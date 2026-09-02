'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { createPage } from '../services/dealerKitService';

/** Lowercase, hyphen-separated, no leading/trailing hyphen - matches the backend validator. */
function toSlug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export function NewPageDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [slugTouched, setSlugTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setName('');
      setSlug('');
      setSlugTouched(false);
      setError(null);
    }
  }, [open]);

  // The address follows the name until someone edits it by hand, after which it
  // is theirs - silently rewriting a deliberate address would be worse than
  // making them type it once.
  const effectiveSlug = slugTouched ? slug : toSlug(name);

  const submit = async () => {
    setError(null);
    setSaving(true);
    try {
      const page = await createPage(name.trim(), effectiveSlug);
      await queryClient.invalidateQueries({ queryKey: ['dealer-kit', 'pages'] });
      toast.success(`Created ${page.name}`);
      onOpenChange(false);
      router.push(`/dealer-kit/pages/${page.id}`);
    } catch (createError) {
      setError(
        createError instanceof Error ? createError.message : 'Could not create the page',
      );
    } finally {
      setSaving(false);
    }
  };

  const canSubmit = name.trim().length > 0 && effectiveSlug.length > 0 && !saving;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Scrollable and height-capped so the submit button stays reachable on a phone. */}
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New catalogue page</DialogTitle>
          <DialogDescription>
            A page is one publishable catalogue. You can lay it out after creating it.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="dk-page-name">Name</Label>
            <Input
              id="dk-page-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Bathroom Catalogue 2026"
              autoFocus
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="dk-page-slug">Address</Label>
            <Input
              id="dk-page-slug"
              value={effectiveSlug}
              onChange={(event) => {
                setSlugTouched(true);
                setSlug(toSlug(event.target.value));
              }}
              placeholder="2026-bathroom"
            />
            <p className="text-xs text-muted-foreground">
              Readers will find this page at /c/{effectiveSlug || '…'}
            </p>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {saving ? 'Creating' : 'Create page'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
