/**
 * Superadmin / admin detection from the NextAuth session.
 *
 * The backend gates company management on the role SLUG (`superadmin`/`admin` - 
 * see UserPermissionService.SUPERADMIN_ROLE_SLUG); there is no dedicated
 * permission slug for it. The session only carries the primary role's display
 * name (`roleName`, e.g. "Super Admin" / "Admin"), so we match case-insensitively
 * against both the slug and display forms.
 *
 * This is a best-effort UX gate only - the backend is the real enforcement
 * (my-context / CRUD return 403 for non-superadmins).
 *
 * TODO(AC-A1/A4): replace with a `system.companies.manage` permission slug once
 * the backend defines one (PLAN-multi-company-isolation.md). A role-name match
 * misses multi-role superadmins whose primary role isn't the superadmin one.
 */
const SUPERADMIN_TOKENS = new Set(['superadmin', 'super admin', 'admin']);

export function isSuperadminUser(user?: { roleName?: string | null } | null): boolean {
  const name = (user?.roleName ?? '').trim().toLowerCase();
  return SUPERADMIN_TOKENS.has(name);
}
