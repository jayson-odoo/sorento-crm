import { useSession } from 'next-auth/react';
import { useHasPermission } from '@/hooks/usePermissions';
import { isSuperadminUser } from '@/lib/is-superadmin';

/** View, capture, vote and comment stay on the board permission (the sidebar entry's own). */
export const IDEAS_VIEW_PERMISSION = 'ideation.board.view';

/**
 * Triage actions: status move, edit, merge/unmerge, board reorder, archive, delete, promote.
 * Q2 is open with the owner; if the answer is "everyone who can view", change this one line to
 * `IDEAS_VIEW_PERMISSION`.
 */
export const IDEAS_MANAGE_PERMISSION = 'ideation.ideas.manage';

export function useCanManageIdeas(): boolean {
  const holds = useHasPermission(IDEAS_MANAGE_PERMISSION);
  const { data: session } = useSession();
  // Phase 1: the slug is not seeded yet, so an admin session stands in for it. Phase 2 seeds the
  // permission and this fallback goes.
  return holds || isSuperadminUser(session?.user);
}
