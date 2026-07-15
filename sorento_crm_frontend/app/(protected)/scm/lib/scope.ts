/**
 * Product-lifecycle scope helpers.
 *
 * The dashboard silently narrows to the FOCUSED view by default (active +
 * ongoing) so inactive / discontinued SKUs never inflate the headline counts.
 * Because that narrowing is invisible, the UI shows a scope chip near the
 * headline tiles (see `ScmScopeChip`) so the user always knows why a count is
 * what it is, with one-click "Show all" / reset.
 */
import type { ScmFilters } from '../services/scmDashboardService';

/** The focused default = active + ongoing (matches the backend default). */
export function isFocusedScope(filters: Pick<ScmFilters, 'activeStatus' | 'lifecycle'>): boolean {
  return filters.activeStatus === 'active' && filters.lifecycle === 'ongoing';
}

/** True when the scope has been widened to every SKU (both filters = all). */
export function isAllScope(filters: Pick<ScmFilters, 'activeStatus' | 'lifecycle'>): boolean {
  return filters.activeStatus === 'all' && filters.lifecycle === 'all';
}

const ACTIVE_LABEL: Record<ScmFilters['activeStatus'], string> = {
  active: 'Active',
  inactive: 'Inactive',
  all: 'All statuses',
};
const LIFECYCLE_LABEL: Record<ScmFilters['lifecycle'], string> = {
  ongoing: 'excluding discontinued',
  discontinued: 'discontinued only',
  all: 'all lifecycle',
};

/** Human-readable one-line summary of the current lifecycle scope. */
export function scopeSummary(filters: Pick<ScmFilters, 'activeStatus' | 'lifecycle'>): string {
  if (isFocusedScope(filters)) return 'Active · excluding discontinued';
  if (isAllScope(filters)) return 'All products';
  return `${ACTIVE_LABEL[filters.activeStatus]} · ${LIFECYCLE_LABEL[filters.lifecycle]}`;
}
