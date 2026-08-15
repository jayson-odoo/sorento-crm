'use client';

import { useEffect, useState } from 'react';
import { Pencil } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import {
  useContactMediaAccess,
  useUpdateContactMediaAccess,
} from '../hooks/useContactMediaAccess';
import {
  MEDIA_MODALITY_LABELS,
  type ContactMediaAccessItem,
} from '../services/contactMediaAccessService';

/**
 * Contact Details -> Media Access (UAC S1-01 .. S1-03).
 *
 * The operator arrives here from a support question - "why did the bot stop reading
 * my photos" - so the answer to it is the first thing on the card: whether each
 * modality is on, how much of this period's allowance has gone, and whether the
 * limit is the inherited default or an override someone set.
 *
 * Both modalities render whether or not the contact has a limit row. Nothing is on
 * for anybody at the start, so hiding the untouched one would hide the whole
 * feature from the person who came to turn it on.
 *
 * Turning a modality ON is one click. Turning it OFF stops the bot reading that
 * dealer's media, so it goes through an AlertDialog rather than a bare switch.
 */
export default function ContactMediaAccessSection({ contactId }: { contactId: string }) {
  const { data, isLoading, isError } = useContactMediaAccess(contactId);
  const update = useUpdateContactMediaAccess(contactId);

  const [editing, setEditing] = useState<ContactMediaAccessItem | null>(null);
  const [confirmingOff, setConfirmingOff] = useState<ContactMediaAccessItem | null>(null);

  function setAllowed(item: ContactMediaAccessItem, allowed: boolean) {
    if (!allowed) {
      setConfirmingOff(item);
      return;
    }
    update.mutate({
      modality: item.modality,
      input: {
        is_allowed: true,
        monthly_limit: item.monthly_limit,
        max_clip_seconds: item.max_clip_seconds,
      },
    });
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <p className="text-sm text-destructive">
        Media access could not be loaded. Reload the page to try again.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {data.items.map((item) => (
          <ModalityPanel
            key={item.modality}
            item={item}
            resetsOn={data.resets_on}
            isSaving={update.isPending}
            onToggle={(allowed) => setAllowed(item, allowed)}
            onEdit={() => setEditing(item)}
          />
        ))}
      </div>

      <MediaLimitsDialog
        item={editing}
        onOpenChange={(open) => {
          if (!open) setEditing(null);
        }}
        isSaving={update.isPending}
        onSave={async (input) => {
          if (!editing) return;
          await update.mutateAsync({ modality: editing.modality, input });
          setEditing(null);
        }}
      />

      <AlertDialog
        open={confirmingOff !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmingOff(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Turn off {confirmingOff ? MEDIA_MODALITY_LABELS[confirmingOff.modality].toLowerCase() : ''}?</AlertDialogTitle>
            <AlertDialogDescription>
              The bot will stop reading{' '}
              {confirmingOff ? MEDIA_MODALITY_LABELS[confirmingOff.modality].toLowerCase() : ''}{' '}
              from this contact and will tell them to type instead.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={update.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                if (!confirmingOff) return;
                update.mutate(
                  {
                    modality: confirmingOff.modality,
                    input: {
                      is_allowed: false,
                      monthly_limit: confirmingOff.monthly_limit,
                      max_clip_seconds: confirmingOff.max_clip_seconds,
                    },
                  },
                  { onSuccess: () => setConfirmingOff(null) },
                );
              }}
              disabled={update.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Turn off
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function ModalityPanel({
  item,
  resetsOn,
  isSaving,
  onToggle,
  onEdit,
}: {
  item: ContactMediaAccessItem;
  resetsOn: string;
  isSaving: boolean;
  onToggle: (allowed: boolean) => void;
  onEdit: () => void;
}) {
  const label = MEDIA_MODALITY_LABELS[item.modality];
  const switchId = `media-access-${item.modality}`;
  const spent = item.used >= item.effective_monthly_limit;

  return (
    <div className="rounded-lg border p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="font-medium">{label}</p>
          {item.is_allowed ? (
            <Badge variant="success" appearance="ghost" className="mt-1 font-normal">
              Enabled
            </Badge>
          ) : (
            <Badge variant="secondary" appearance="ghost" className="mt-1 font-normal">
              Not enabled
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Switch
            id={switchId}
            aria-label={`Enable ${label.toLowerCase()}`}
            checked={item.is_allowed}
            disabled={isSaving}
            onCheckedChange={onToggle}
          />
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            aria-label={`Edit ${label.toLowerCase()} limits`}
            onClick={onEdit}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <dl className="mt-3 space-y-1.5 text-sm">
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-muted-foreground">Used this month</dt>
          <dd className={`tabular-nums font-medium ${spent ? 'text-destructive' : ''}`}>
            {item.used} of {item.effective_monthly_limit}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-muted-foreground">Resets</dt>
          <dd className="font-medium">{resetsOn}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-muted-foreground">Monthly limit</dt>
          <dd className="font-medium">
            {item.monthly_limit === null
              ? `Default (${item.effective_monthly_limit})`
              : `Override (${item.monthly_limit})`}
          </dd>
        </div>
        {item.modality === 'voice' ? (
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-muted-foreground">Maximum clip</dt>
            <dd className="font-medium">
              {item.max_clip_seconds !== null
                ? `Override (${item.max_clip_seconds}s)`
                : item.effective_max_clip_seconds === null
                  ? 'Default'
                  : `Default (${item.effective_max_clip_seconds}s)`}
            </dd>
          </div>
        ) : null}
      </dl>

      <p className="mt-3 text-xs text-muted-foreground">
        {item.has_row && item.updated_at
          ? `Last changed ${formatDateTimeInMalaysia(item.updated_at)}${
              item.updated_by_name ? ` by ${item.updated_by_name}` : ''
            }`
          : 'Never configured - this contact is on the system default.'}
      </p>
    </div>
  );
}

/**
 * Blank is always valid here - it clears the override and inherits the default.
 * Anything else is held to the bounds the PUT already enforces, so an out-of-range
 * override is refused inline instead of coming back as a 422 to interpret.
 */
function boundedError(raw: string, min: number, max: number): string | undefined {
  const trimmed = raw.trim();
  if (trimmed === '') return undefined;
  const message = `Enter a whole number between ${min} and ${max}, or leave it blank.`;
  if (!/^\d+$/.test(trimmed)) return message;
  const value = Number(trimmed);
  return value < min || value > max ? message : undefined;
}

function MediaLimitsDialog({
  item,
  onOpenChange,
  isSaving,
  onSave,
}: {
  item: ContactMediaAccessItem | null;
  onOpenChange: (open: boolean) => void;
  isSaving: boolean;
  onSave: (input: {
    is_allowed: boolean;
    monthly_limit: number | null;
    max_clip_seconds: number | null;
  }) => void | Promise<void>;
}) {
  const [limit, setLimit] = useState('');
  const [clipSeconds, setClipSeconds] = useState('');

  useEffect(() => {
    if (!item) return;
    setLimit(item.monthly_limit === null ? '' : String(item.monthly_limit));
    setClipSeconds(item.max_clip_seconds === null ? '' : String(item.max_clip_seconds));
  }, [item]);

  const limitError = boundedError(limit, 0, 100000);
  const clipError = boundedError(clipSeconds, 1, 3600);
  const label = item ? MEDIA_MODALITY_LABELS[item.modality] : '';

  // The default is the effective limit, and only while no override is set - once
  // one is, the effective number IS the override and the API does not carry the
  // default alongside it. Naming a number the operator can change on the settings
  // page would go stale the moment they did, so it is named only when it is known.
  const defaultLimit = item && item.monthly_limit === null ? item.effective_monthly_limit : null;
  const defaultClipSeconds =
    item && item.max_clip_seconds === null ? item.effective_max_clip_seconds : null;

  return (
    <Dialog open={item !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{label ? `${label} limits` : 'Limits'}</DialogTitle>
          <DialogDescription>Overrides the system default for this contact.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="media-monthly-limit">Monthly limit</Label>
            <Input
              id="media-monthly-limit"
              inputMode="numeric"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              aria-invalid={Boolean(limitError)}
              aria-describedby="media-monthly-limit-hint"
              placeholder={defaultLimit === null ? '' : String(defaultLimit)}
            />
            <p
              id="media-monthly-limit-hint"
              className={`text-xs ${limitError ? 'text-destructive' : 'text-muted-foreground'}`}
            >
              {limitError ??
                `Blank uses the system default${
                  defaultLimit === null ? '' : ` (${defaultLimit})`
                }.`}
            </p>
          </div>
          {item?.modality === 'voice' ? (
            <div className="space-y-2">
              <Label htmlFor="media-clip-seconds">Maximum clip seconds</Label>
              <Input
                id="media-clip-seconds"
                inputMode="numeric"
                value={clipSeconds}
                onChange={(e) => setClipSeconds(e.target.value)}
                aria-invalid={Boolean(clipError)}
                aria-describedby="media-clip-seconds-hint"
                placeholder={defaultClipSeconds === null ? '' : String(defaultClipSeconds)}
              />
              <p
                id="media-clip-seconds-hint"
                className={`text-xs ${clipError ? 'text-destructive' : 'text-muted-foreground'}`}
              >
                {clipError ??
                  `Blank uses the system default${
                    defaultClipSeconds === null ? '' : ` (${defaultClipSeconds}s)`
                  }. A longer clip is refused before anything is spent.`}
              </p>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
            Cancel
          </Button>
          <Button
            disabled={isSaving || Boolean(limitError) || Boolean(clipError)}
            onClick={() => {
              if (!item) return;
              void onSave({
                is_allowed: item.is_allowed,
                monthly_limit: limit.trim() === '' ? null : Number(limit.trim()),
                max_clip_seconds:
                  item.modality !== 'voice' || clipSeconds.trim() === ''
                    ? null
                    : Number(clipSeconds.trim()),
              });
            }}
          >
            {isSaving ? 'Saving…' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
