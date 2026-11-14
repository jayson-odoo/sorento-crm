/** WA-COMPLAINT-INTAKE B-4: Type is read through ONE helper; no type data reads as an idea. */
import { describe, it, expect } from 'vitest';
import { ideaType, IDEA_TYPE_LABEL } from './ideaType';
import type { Idea } from '@/types/ideas';

const asIdea = (over: Record<string, unknown>) => over as unknown as Idea;

describe('ideaType helper (B-4)', () => {
  it('labels are Feature request and Issue', () => {
    expect(IDEA_TYPE_LABEL).toEqual({ idea: 'Feature request', issue: 'Problem report' });
  });
  it('reads issue and idea as sent', () => {
    expect(ideaType(asIdea({ type: 'issue' }))).toBe('issue');
    expect(ideaType(asIdea({ type: 'idea' }))).toBe('idea');
  });
  it('missing, null or unknown type reads idea', () => {
    expect(ideaType(asIdea({}))).toBe('idea');
    expect(ideaType(asIdea({ type: null }))).toBe('idea');
    expect(ideaType(asIdea({ type: 'bug' }))).toBe('idea');
  });
});
