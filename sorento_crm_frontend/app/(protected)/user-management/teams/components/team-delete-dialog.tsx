'use client';

import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { LoaderCircleIcon } from 'lucide-react';
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
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => (team ? deleteTeam(team.id) : Promise.resolve()),
    onSuccess: () => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="success">
            <AlertIcon>
              <RiCheckboxCircleFill />
            </AlertIcon>
            <AlertTitle>Team deleted successfully</AlertTitle>
          </Alert>
        ),
        { position: 'top-center', duration: 5000 },
      );
      queryClient.invalidateQueries({ queryKey: ['user-management-teams'] });
      closeDialog();
    },
    onError: (error: Error) => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="destructive">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertTitle>{error.message}</AlertTitle>
          </Alert>
        ),
        { position: 'top-center' },
      );
    },
  });

  if (!team) return null;

  return (
    <Dialog open={open} onOpenChange={closeDialog}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete team</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Are you sure you want to delete the team <strong>{team.name}</strong>? Members will be
          removed from this team.
        </DialogDescription>
        <DialogFooter>
          <Button variant="outline" onClick={closeDialog}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending && <LoaderCircleIcon className="animate-spin me-2" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
