'use client';

import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { getUserLookup } from '@/services/userSelectService';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useTakeoverMutations,
  useTakeoverRequests,
  useUpdateProject,
} from '../../_shared/hooks/useProjects';
import type { Project } from '../../_shared/types/project.types';
import { projectCodeLabel } from '../../_shared/lib/projectCode';

/**
 * Hand the project to another salesperson (owner, 13 Oct: "how do I reassign the project").
 *
 * The same write the project form's Salesperson field makes, so the server's rule applies
 * unchanged: only `projects.projects.manage` may move an owner. The caller shows the entry
 * to managers only; the server refuses anyone else with a 403 the mutation toasts.
 *
 * People who registered interest come first, with their date (PROJECT-REGISTER-V2 E5);
 * picking one rules on that interest, picking anyone else is today's owner update.
 */
export function ReassignProjectDialog({
  project,
  onDone,
}: {
  project: Project;
  onDone: () => void;
}) {
  const update = useUpdateProject(project.id);
  const { decide } = useTakeoverMutations(project.id);
  const requests = useTakeoverRequests(project.id);
  const [ownerUserId, setOwnerUserId] = React.useState(project.owner_user_id ?? '');
  const users = useQuery({
    queryKey: ['user-lookup', 'project-owner'],
    queryFn: () => getUserLookup(),
  });

  const interests = (requests.data ?? []).filter(
    (request) => request.status === 'pending' && request.kind === 'dispute',
  );
  const interestByUser = new Map(interests.map((request) => [request.requester_user_id, request]));
  const everyone = users.data ?? [];
  const interestedOptions = interests.map((request) => ({
    value: request.requester_user_id,
    label: request.requester_name ?? everyone.find((u) => u.id === request.requester_user_id)?.name ?? 'Unnamed user',
    description: request.created_at ? formatDateInMalaysia(request.created_at) : undefined,
  }));
  const otherOptions = everyone
    .filter((user) => !interestByUser.has(user.id))
    .map((user) => ({ value: user.id, label: user.name || 'Unnamed user' }));

  const changed = Boolean(ownerUserId) && ownerUserId !== (project.owner_user_id ?? '');
  const pending = update.isPending || decide.isPending;

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="w-full max-w-md" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Reassign {projectCodeLabel(project)}</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (!changed) return;
            try {
              const interest = interestByUser.get(ownerUserId);
              if (interest) await decide.mutateAsync({ id: interest.id, approve: true });
              else await update.mutateAsync({ owner_user_id: ownerUserId });
              onDone();
            } catch {
              // toasted by the mutation; the dialog stays open with the pick
            }
          }}
        >
          <DialogBody className="space-y-1.5">
            <Label htmlFor="reassign-owner">Salesperson</Label>
            <SearchableSelect
              id="reassign-owner"
              value={ownerUserId}
              onChange={setOwnerUserId}
              loadError={users.error}
              onRetry={() => void users.refetch()}
              options={[...interestedOptions, ...otherOptions]}
              placeholder="Select a salesperson"
              emptyMessage="No match"
            />
          </DialogBody>
          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!changed || pending}>
              {pending && <Loader2 className="size-4 animate-spin" aria-hidden />}
              Reassign
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
