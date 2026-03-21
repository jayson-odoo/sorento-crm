'use client';

import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useDeleteAccessAgent } from '../hooks/useAccessAgents';
import type { AccessAgent } from '../types/accessAgent.types';

export interface AccessAgentDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  accessAgent: AccessAgent;
  onSuccess?: () => void;
}

export default function AccessAgentDeleteDialog({
  open,
  closeDialog,
  accessAgent,
  onSuccess,
}: AccessAgentDeleteDialogProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const deleteMutation = useDeleteAccessAgent();

  const handleDelete = async () => {
    await deleteMutation.mutateAsync(accessAgent.id);
  };

  return (
    <ConfirmDeleteDialog
      open={open}
      onOpenChange={(o) => !o && closeDialog()}
      title="Confirm Delete"
      description={
        <>
          Are you sure you want to delete the access agent <strong>{accessAgent.name}</strong> ({accessAgent.code})?
          This action cannot be undone.
        </>
      }
      onDelete={handleDelete}
      queryKeysToInvalidate={[['access-agents']]}
      successMessage="Access agent deleted successfully"
      onSuccess={() => {
        onSuccess?.();
        router.push('/user-management/access-agents');
        // After leaving the detail route, drop caches (avoid refetch-404 noise if user was still subscribed briefly).
        queryClient.removeQueries({ queryKey: ['access-agent', accessAgent.id] });
        queryClient.removeQueries({ queryKey: ['agent-teams', accessAgent.id] });
        queryClient.removeQueries({ queryKey: ['contact-access-agents', accessAgent.id] });
      }}
    />
  );
}
