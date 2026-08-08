/**
 * The sidebar claiming you are in two places at once.
 *
 * The old rule was `path === pathname || pathname.startsWith(path)`. Standing on
 * `/complaint-management/service-jobs/board` matched "Dispatch Board" AND "Service Jobs",
 * because one path is a literal prefix of the other, and both rendered highlighted.
 *
 * This is not a service-jobs quirk. Any listing that grows a sub-route hits it, so the fix
 * is here rather than in one menu entry.
 */
import { describe, expect, it } from 'vitest';

import { collectMenuPaths, createMatchPath, isSegmentPrefix } from './menu-active-path';

const MENU = [
  {
    title: 'Complaint Management',
    children: [
      { title: 'Complaints', path: '/complaint-management/complaints' },
      { title: 'Service Jobs', path: '/complaint-management/service-jobs' },
      { title: 'Dispatch Board', path: '/complaint-management/service-jobs/board' },
      { title: 'Technicians', path: '/complaint-management/technicians' },
    ],
  },
];

const PATHS = collectMenuPaths(MENU);

describe('the two-places-at-once bug', () => {
  it('highlights only the board when standing on the board', () => {
    const match = createMatchPath('/complaint-management/service-jobs/board', PATHS);
    expect(match('/complaint-management/service-jobs/board')).toBe(true);
    expect(match('/complaint-management/service-jobs')).toBe(false);
  });

  it('highlights the list when standing on the list', () => {
    const match = createMatchPath('/complaint-management/service-jobs', PATHS);
    expect(match('/complaint-management/service-jobs')).toBe(true);
    expect(match('/complaint-management/service-jobs/board')).toBe(false);
  });

  it('still highlights the list from a detail page under it', () => {
    // A detail route has no menu entry of its own, and the list is the honest answer -
    // this is the behaviour the old prefix rule got right and must not be lost.
    const match = createMatchPath('/complaint-management/service-jobs/abc-123', PATHS);
    expect(match('/complaint-management/service-jobs')).toBe(true);
    expect(match('/complaint-management/service-jobs/board')).toBe(false);
  });

  it('does not leak across an unrelated sibling that shares a name prefix', () => {
    // `/service-jobs-archive` is not under `/service-jobs`, however much `startsWith`
    // would like it to be.
    const match = createMatchPath('/complaint-management/service-jobs-archive', PATHS);
    expect(match('/complaint-management/service-jobs')).toBe(false);
  });

  it('leaves other groups alone', () => {
    const match = createMatchPath('/complaint-management/technicians', PATHS);
    expect(match('/complaint-management/complaints')).toBe(false);
    expect(match('/complaint-management/technicians')).toBe(true);
  });
});

describe('isSegmentPrefix', () => {
  it('matches a path against itself', () => {
    expect(isSegmentPrefix('/a/b', '/a/b')).toBe(true);
  });

  it('matches an ancestor', () => {
    expect(isSegmentPrefix('/a', '/a/b/c')).toBe(true);
  });

  it('refuses a longer path', () => {
    expect(isSegmentPrefix('/a/b/c', '/a/b')).toBe(false);
  });

  it('refuses a partial segment', () => {
    expect(isSegmentPrefix('/a/b', '/a/bc')).toBe(false);
  });

  it('ignores trailing slashes and query strings', () => {
    expect(isSegmentPrefix('/a/b', '/a/b/')).toBe(true);
    expect(isSegmentPrefix('/a/b', '/a/b?page=2')).toBe(true);
  });
});

describe('collectMenuPaths', () => {
  it('walks into children', () => {
    expect(PATHS).toContain('/complaint-management/service-jobs/board');
    expect(PATHS).toHaveLength(4);
  });

  it('skips group headers that have no path of their own', () => {
    expect(PATHS).not.toContain(undefined);
  });
});

describe('an entry the caller forgot to collect', () => {
  it('falls back to ancestor matching rather than never highlighting', () => {
    // Degrading to the old behaviour for one entry beats a sidebar with nothing selected.
    const match = createMatchPath('/complaint-management/service-jobs/board', []);
    expect(match('/complaint-management/service-jobs')).toBe(true);
  });
});
