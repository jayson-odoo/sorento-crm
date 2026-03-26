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
      const data = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          data?.message ??
            data?.detail ??
            (await extractApiError(response, 'Failed to delete role')),
        );
      }

      const failedByContract =
        data?.success === false ||
        data?.deleted === false ||
        (typeof data?.deleted_count === 'number' && data.deleted_count < 1);

      if (failedByContract) {
        throw new Error(
          data?.message ?? data?.detail ?? 'Role could not be deleted.',
        );
      }

      // Verify backend actually deleted/trashed the role before claiming success.
      const verifyResponse = await apiFetch(
        `/api/user-management/roles/${role.id}?_t=${Date.now()}`,
      );

      if (verifyResponse.ok) {
        const verifyPayload = await verifyResponse.json().catch(() => null);
        const roleAfterDelete = verifyPayload?.data ?? verifyPayload ?? null;
        const isTrashed = Boolean(roleAfterDelete?.isTrashed ?? roleAfterDelete?.is_trashed);
        if (roleAfterDelete?.id && !isTrashed) {
          throw new Error(
            'Role is still active after delete request. It may be protected or currently in use by users.',
          );
        }
      }
    }}
    queryKeysToInvalidate={[['user-roles'], ['user-role-select']]}
    successMessage="Role deleted successfully"
  />
);

export default RoleDeleteDialog;
