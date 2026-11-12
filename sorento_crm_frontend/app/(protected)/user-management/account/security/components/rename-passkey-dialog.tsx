'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useRenamePasskeyMutation } from '@/hooks/usePasskeys';
import type { PasskeyItem } from '@/services/passkeyService';

/** "Rename passkey" (PASSKEY-LOGIN AC-44), the shape of RenameAccessoryTemplateDialog. */
export function RenamePasskeyDialog({
  open,
  onOpenChange,
  passkey,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  passkey: PasskeyItem | null;
}) {
  const [name, setName] = useState('');
  const rename = useRenamePasskeyMutation();

  useEffect(() => {
    if (!open) return;
    setName(passkey?.name ?? '');
  }, [open, passkey]);

  const submit = async () => {
    if (!passkey) return;
    try {
      await rename.mutateAsync({ id: passkey.id, name: name.trim() });
      onOpenChange(false);
    } catch {
      // The hook has already shown the backend's message.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Rename passkey</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-2 py-2">
          <Label htmlFor="passkey-name">Name</Label>
          <Input
            id="passkey-name"
            value={name}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={rename.isPending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!name.trim() || rename.isPending}>
            {rename.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
