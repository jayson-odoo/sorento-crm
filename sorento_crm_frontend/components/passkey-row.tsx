'use client';

/**
 * One passkey in a list (PASSKEY-LOGIN AC-43 / AC-45): device icon, name, when it was added and
 * last used, and a row menu. Shared by My account > Security and the admin's Sign-in card.
 * Remove is the deferred record action `user_passkey.delete` (countdown with Cancel, no
 * confirm dialog); Rename is offered only where `onRename` is given.
 */

import { Ellipsis, Laptop, Smartphone } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import DeferredActionButton from '@/components/common/DeferredActionButton';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import type { PasskeyItem } from '@/services/passkeyService';

const PHONE_WORDS = /iphone|ipad|android|phone/i;

export default function PasskeyRow({
  passkey,
  canRemove,
  onRename,
  invalidateKeys,
}: {
  passkey: PasskeyItem;
  canRemove: boolean;
  onRename?: (passkey: PasskeyItem) => void;
  invalidateKeys: readonly (readonly unknown[])[];
}) {
  const remove = useDeferredAction({
    actionKey: 'user_passkey.delete',
    entityType: 'user_passkey',
    entityId: passkey.id,
    verb: 'Removing',
    subject: passkey.name,
    surface: 'inline',
    successMessage: 'Passkey removed',
    invalidateKeys,
  });

  const Icon = PHONE_WORDS.test(passkey.name) ? Smartphone : Laptop;
  const hasMenu = canRemove || Boolean(onRename);

  return (
    // flex-wrap: at 375px a running countdown ("Removing in 10s" + Cancel) takes its own line
    // under the text instead of squeezing the name and dates.
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3">
      <Icon
        className="size-5 shrink-0 text-muted-foreground"
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1 text-sm">
        <div className="truncate font-medium" title={passkey.name}>
          {passkey.name}
        </div>
        <div className="text-muted-foreground">
          {passkey.created_at
            ? `Added ${formatDateInMalaysia(passkey.created_at)}`
            : null}
        </div>
        <div className="text-muted-foreground">
          {passkey.last_used_at
            ? `Last used ${formatDateTimeInMalaysia(passkey.last_used_at)}`
            : 'Never used'}
        </div>
      </div>
      {hasMenu && (
        <div
          className={
            remove.pending ? 'w-full pl-8 sm:w-auto sm:pl-0' : 'shrink-0'
          }
        >
          <DeferredActionButton
            pending={remove.pending}
            verb="Removing"
            onCancel={remove.cancel}
            idle={
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    aria-label="Passkey options"
                  >
                    <Ellipsis />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent side="bottom" align="end">
                  {onRename && (
                    <DropdownMenuItem onClick={() => onRename(passkey)}>
                      Rename
                    </DropdownMenuItem>
                  )}
                  {canRemove && (
                    <DropdownMenuItem
                      variant="destructive"
                      disabled={remove.isBlocked}
                      onClick={() => remove.start()}
                    >
                      Remove
                    </DropdownMenuItem>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            }
          />
        </div>
      )}
    </li>
  );
}
