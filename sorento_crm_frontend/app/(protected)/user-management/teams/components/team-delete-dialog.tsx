'use client';

import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import type { Team } from '../types/team.types';
import { deleteTeam } from '../services/teamService';

export default function TeamDeleteDialog({
  open,
  closeDialog,
  team,
}: {
  open: boolean;
  closeDialog: () => void;
  team: Team | null;
}) {
  if (!team) return null;

  return (
    <ConfirmDeleteDialog
      open={open}
      onOpenChange={(o) => !o && closeDialog()}
      title="Delete team"
      description={
        <>
          Are you sure you want to delete the team <strong>{team.name}</strong>? Members will be
          removed from this team.
        </>
      }
      onDelete={() => deleteTeam(team.id)}
      queryKeysToInvalidate={[['user-management-teams']]}
      successMessage="Team deleted successfully"
    />
  );
}
