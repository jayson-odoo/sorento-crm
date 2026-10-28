/**
 * RW (PLAN R2): a portal registration has no project code until Approve, and every screen shows
 * "Awaiting approval" where the code would be, through ONE helper. "None", "null" and an empty
 * slot are all defects.
 */
import { describe, expect, it } from 'vitest';
import { projectCodeLabel } from './projectCode';

describe('projectCodeLabel', () => {
  it('is the code once the project has one', () => {
    expect(projectCodeLabel({ project_code: 'PPF2610005' })).toBe('PPF2610005');
    expect(projectCodeLabel({ project_code: 'PRJ-000142' })).toBe('PRJ-000142');
  });

  it.each([
    ['null', { project_code: null }],
    ['undefined', { project_code: undefined }],
    ['an empty string', { project_code: '' }],
    ['blank spaces', { project_code: '   ' }],
  ])('is "Awaiting approval" for %s', (_name, project) => {
    expect(projectCodeLabel(project)).toBe('Awaiting approval');
  });

  it('never renders the words None or null', () => {
    for (const code of [null, undefined, '']) {
      expect(projectCodeLabel({ project_code: code })).not.toMatch(/none|null|undefined/i);
    }
  });

  it('does not trim a real code', () => {
    expect(projectCodeLabel({ project_code: ' PPF2610005 ' }).trim()).toBe('PPF2610005');
  });
});

describe('projectCodeLabel on a rejected registration (review round 3)', () => {
  it('reads Rejected where the code would be', () => {
    expect(projectCodeLabel({ project_code: null, approval_state: 'rejected' })).toBe('Rejected');
  });
  it('reads Awaiting approval for a pending or a draft one', () => {
    expect(projectCodeLabel({ project_code: null, approval_state: 'pending' })).toBe('Awaiting approval');
    expect(projectCodeLabel({ project_code: null, approval_state: 'draft' })).toBe('Awaiting approval');
  });
  it('a code always wins', () => {
    expect(projectCodeLabel({ project_code: 'PPF2610005', approval_state: 'approved' })).toBe('PPF2610005');
  });
});

describe('projectCodeLabel on a resubmitted registration (RESUBMITTED-STATUS)', () => {
  it('reads Appealed where the code would be', () => {
    expect(projectCodeLabel({ project_code: null, approval_state: 'resubmitted' })).toBe('Appealed');
  });
});
