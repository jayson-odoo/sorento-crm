/** R6 (review round 3): the detail page's pager walks the same approval-filtered list. */
import { describe, expect, it } from 'vitest';
import { projectsListParamsFromUrl } from './useProjects';

const base = { pageIndex: 0, pageSize: 50, sorting: [], searchQuery: '' };

describe('projectsListParamsFromUrl', () => {
  it('carries the approval_state filter from the URL', () => {
    expect(
      projectsListParamsFromUrl({ ...base, filters: { approval_state: 'pending' } } as never).approval_state,
    ).toBe('pending');
  });

  it('leaves it out when the URL has none', () => {
    expect(projectsListParamsFromUrl({ ...base, filters: {} } as never).approval_state).toBeUndefined();
  });
});
