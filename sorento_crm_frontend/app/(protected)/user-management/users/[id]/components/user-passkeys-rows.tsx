'use client';

/**
 * The Sign-in card's two passkey rows (PASSKEY-LOGIN AC-45): "Passkey sign-in" (the per-user
 * switch, editable with `user_management.users.edit`) and "Passkeys" (a count that opens the
 * list, with Remove for `users.edit`). Admins never add or rename someone's passkey.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';
import PasskeyRow from '@/components/passkey-row';
import {
  useSetUserPasskeyEnabledMutation,
  useUserPasskeysQuery,
  userPasskeysKey,
} from '@/hooks/usePasskeys';
import type { User } from '@/app/models/user';

export default function UserPasskeysRows({ user, canEdit }: { user: User; canEdit: boolean }) {
  const [open, setOpen] = useState(false);
  const setEnabled = useSetUserPasskeyEnabledMutation();
  const list = useUserPasskeysQuery(user.id, open);

  const on = setEnabled.isPending
    ? Boolean(setEnabled.variables?.enabled)
    : Boolean(user.passkeyEnabled);
  const count = user.passkeyCount ?? 0;
  const invalidateKeys = [userPasskeysKey(user.id), ['user-user', user.id]];

  return (
    <>
      <dt>Passkey sign-in</dt>
      <dd>
        {canEdit ? (
          <Switch
            size="sm"
            checked={on}
            disabled={setEnabled.isPending}
            onCheckedChange={(enabled) => setEnabled.mutate({ userId: user.id, enabled })}
            aria-label="Passkey sign-in"
          />
        ) : (
          <span>{on ? 'On' : 'Off'}</span>
        )}
      </dd>

      <dt>Passkeys</dt>
      <dd>
        {count > 0 ? (
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto p-0"
            onClick={() => setOpen(true)}
          >
            {count === 1 ? '1 passkey' : `${count} passkeys`}
          </Button>
        ) : (
          <span className="text-muted-foreground">None</span>
        )}
      </dd>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Passkeys</DialogTitle>
          </DialogHeader>
          {list.isError ? (
            <p className="text-sm text-destructive">{list.error.message}</p>
          ) : (list.data ?? []).length === 0 && !list.isLoading ? (
            <div className="py-4 text-center">
              <p className="text-sm font-medium">No passkeys</p>
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {(list.data ?? []).map((p) => (
                <PasskeyRow
                  key={p.id}
                  passkey={p}
                  canRemove={canEdit}
                  invalidateKeys={invalidateKeys}
                />
              ))}
            </ul>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
