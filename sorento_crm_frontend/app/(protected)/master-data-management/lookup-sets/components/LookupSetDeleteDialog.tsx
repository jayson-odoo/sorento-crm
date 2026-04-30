'use client';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { deleteLookupSet } from '../services/lookupSetService';
import type { LookupSet } from '../types/lookup.types';

export default function LookupSetDeleteDialog({
  open,
  closeDialog,
  set,
}: {
  open: boolean;
  closeDialog: () => void;
  set: LookupSet;
}) {
  return (
    <ConfirmDeleteDialog
      open={open}
      onOpenChange={(o) => {
        if (!o) closeDialog();
      }}
      title="Delete lookup set?"
      description={`This will permanently delete "${set.name}" along with its options, keywords, and bindings. This action cannot be undone.`}
      onDelete={() => deleteLookupSet(set.id)}
      queryKeysToInvalidate={[['lookup-sets']]}
      successMessage="Lookup set deleted"
      onSuccess={closeDialog}
    />
  );
}
