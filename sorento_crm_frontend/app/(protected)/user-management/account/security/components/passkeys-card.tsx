'use client';

/**
 * "Passkeys" on My account > Security (PASSKEY-LOGIN AC-43 / AC-44): the signed-in (real)
 * user's passkeys. Shown by the page only while the user's passkey sign-in is on.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { ListLoadFailure } from '@/components/common/ListLoadFailure';
import PasskeyRow from '@/components/passkey-row';
import { MY_PASSKEYS_KEY, useMyPasskeysQuery, usePasskeyStatusQuery } from '@/hooks/usePasskeys';
import { browserCanUsePasskeys } from '@/lib/passkey';
import type { PasskeyItem } from '@/services/passkeyService';
import { AddPasskeyDialog } from './add-passkey-dialog';
import { RenamePasskeyDialog } from './rename-passkey-dialog';

const INVALIDATE = [MY_PASSKEYS_KEY];

export default function PasskeysCard({ hasPassword }: { hasPassword: boolean }) {
  const [supported] = useState(browserCanUsePasskeys);
  const status = usePasskeyStatusQuery(supported);
  const list = useMyPasskeysQuery();
  const [adding, setAdding] = useState(false);
  const [renaming, setRenaming] = useState<PasskeyItem | null>(null);

  const unavailable = !supported || status.data?.enabled === false;
  const canAdd = supported && status.data?.enabled === true;
  const passkeys = list.data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle>Passkeys</CardTitle>
        </CardHeading>
        <Button variant="outline" size="sm" disabled={!canAdd} onClick={() => setAdding(true)}>
          Add passkey
        </Button>
      </CardHeader>
      <CardContent className="space-y-2">
        {unavailable && (
          <p className="text-sm text-muted-foreground">This browser can&apos;t use passkeys.</p>
        )}
        {list.isError ? (
          <ListLoadFailure error={list.error} onRetry={() => void list.refetch()} />
        ) : list.isLoading ? null : passkeys.length === 0 ? (
          <div className="py-4 text-center">
            <p className="text-sm font-medium">No passkeys yet</p>
            <p className="text-sm text-muted-foreground">
              Sign in with Face ID, Touch ID or your fingerprint.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {passkeys.map((p) => (
              <PasskeyRow
                key={p.id}
                passkey={p}
                canRemove
                onRename={setRenaming}
                invalidateKeys={INVALIDATE}
              />
            ))}
          </ul>
        )}
      </CardContent>

      <AddPasskeyDialog open={adding} onOpenChange={setAdding} hasPassword={hasPassword} />
      <RenamePasskeyDialog
        open={renaming !== null}
        onOpenChange={(open) => !open && setRenaming(null)}
        passkey={renaming}
      />
    </Card>
  );
}
