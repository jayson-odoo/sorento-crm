import * as React from 'react';
import { usePartyRoleLabel, usePartyRoles } from '../../_shared/hooks/useProjects';

/** "main_contractor" -> "Main contractor": an unknown key still reads as words. */
export function humanizeRole(value?: string | null): string {
  if (!value) return '';
  const words = value.replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * The party types to pick from: the active roles of the editable list `project_party_role`
 * (PROJECT-PARTY-ROLES), plus `current` when it is a role switched off since, so an edit never
 * silently retypes the party.
 */
export function usePartyTypeOptions(current?: string | null): { value: string; label: string }[] {
  const roles = usePartyRoles();
  return React.useMemo(
    () =>
      (roles.data ?? [])
        .filter((role) => role.is_active || role.value === current)
        .map((role) => ({ value: role.value, label: role.label })),
    [roles.data, current],
  );
}

export { usePartyRoleLabel };
