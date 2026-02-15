'use client';

import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { UserRole } from '@/app/models/user';

const RoleDeleteDialog = ({
  open,
  closeDialog,
  role,
}: {
  open: boolean;
  closeDialog: () => void;
  role: UserRole;
}) => (
  <ConfirmDeleteDialog
    open={open}
    onOpenChange={(o) => !o && closeDialog()}
    title="Confirm Delete"
    description={
      <>
        Are you sure you want to delete the role <strong>{role.name}</strong>?
      </>
    }
    onDelete={async () => {
      const response = await apiFetch(`/api/user-management/roles/${role.id}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete role'));
    }}
    queryKeysToInvalidate={[['user-roles']]}
    successMessage="Role deleted successfully"
  />
);

export default RoleDeleteDialog;
