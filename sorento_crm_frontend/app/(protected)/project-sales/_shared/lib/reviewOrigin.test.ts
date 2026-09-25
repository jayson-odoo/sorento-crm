/**
 * S4: the origin a review page returns to after Confirm / Confirm schedule / Publish. Carried
 * as one `from` query param on the review page's own URL - a full relative path (with its own
 * query string) to push back to. Absent means "stay", same as before this slice.
 */
import { describe, expect, it } from 'vitest';
import {
  isSafeReviewOrigin,
  pipelineOriginHref,
  projectTabOriginHref,
  withReviewOrigin,
} from './reviewOrigin';

describe('isSafeReviewOrigin', () => {
  it('accepts a same-app relative path', () => {
    expect(isSafeReviewOrigin('/project-sales/pipeline?from=p1')).toBe(true);
    expect(isSafeReviewOrigin('/project-sales/p1?tab=sales-orders')).toBe(true);
  });

  it('rejects a crafted external origin (S1, open redirect)', () => {
    expect(isSafeReviewOrigin('https://elsewhere.test/steal-session')).toBe(false);
    expect(isSafeReviewOrigin('http://elsewhere.test')).toBe(false);
    expect(isSafeReviewOrigin('//elsewhere.test')).toBe(false);
  });

  it('rejects an empty or absent origin', () => {
    expect(isSafeReviewOrigin(null)).toBe(false);
    expect(isSafeReviewOrigin(undefined)).toBe(false);
    expect(isSafeReviewOrigin('')).toBe(false);
  });
});

describe('withReviewOrigin', () => {
  it('appends the origin as a `from` param on a URL with no query string yet', () => {
    expect(withReviewOrigin('/project-sales/p1/purchase-orders/v1', '/project-sales/pipeline?from=p1')).toBe(
      '/project-sales/p1/purchase-orders/v1?from=%2Fproject-sales%2Fpipeline%3Ffrom%3Dp1',
    );
  });

  it('leaves the URL unchanged with no origin', () => {
    expect(withReviewOrigin('/project-sales/p1/purchase-orders/v1', undefined)).toBe(
      '/project-sales/p1/purchase-orders/v1',
    );
    expect(withReviewOrigin('/project-sales/p1/purchase-orders/v1', null)).toBe(
      '/project-sales/p1/purchase-orders/v1',
    );
  });

  it('round-trips through URLSearchParams: the nested origin reads back exactly', () => {
    const origin = '/project-sales/pipeline?page=1&sort=created_at&dir=desc&from=p1';
    const pushed = withReviewOrigin('/project-sales/p1/purchase-orders/v1', origin);
    const params = new URLSearchParams(pushed.split('?')[1]);
    expect(params.get('from')).toBe(origin);
  });
});

describe('projectTabOriginHref', () => {
  it('builds the project tab origin', () => {
    expect(projectTabOriginHref('p1', 'pos')).toBe('/project-sales/p1?tab=pos');
    expect(projectTabOriginHref('p1', 'schedules')).toBe('/project-sales/p1?tab=schedules');
  });
});

describe('pipelineOriginHref', () => {
  it('names the picked project as `from` on the pipeline list', () => {
    expect(pipelineOriginHref(undefined, 'p1')).toBe('/project-sales/pipeline?from=p1');
  });

  it('carries the pipeline grid\'s own list state alongside the picked project', () => {
    expect(pipelineOriginHref('page=2&sort=created_at&dir=desc', 'p1')).toBe(
      '/project-sales/pipeline?page=2&sort=created_at&dir=desc&from=p1',
    );
  });
});
