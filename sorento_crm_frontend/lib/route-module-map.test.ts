import { describe, expect, it } from 'vitest';

import { moduleKeyForPath } from './route-module-map';

describe('moduleKeyForPath', () => {
  it('maps /dealer-kit/editions to dealer_kit', () => {
    expect(moduleKeyForPath('/dealer-kit/editions')).toBe('dealer_kit');
  });

  it('maps /dealer-kit exactly to dealer_kit', () => {
    expect(moduleKeyForPath('/dealer-kit')).toBe('dealer_kit');
  });

  it('maps /project-sales/pipeline to projects', () => {
    expect(moduleKeyForPath('/project-sales/pipeline')).toBe('projects');
  });

  it('maps /project-sales exactly to projects', () => {
    expect(moduleKeyForPath('/project-sales')).toBe('projects');
  });

  it('returns null for an unknown path', () => {
    expect(moduleKeyForPath('/unknown-route')).toBeNull();
  });

  it('strips query params before matching', () => {
    expect(moduleKeyForPath('/dealer-kit/pages?tab=drafts')).toBe('dealer_kit');
  });
});
