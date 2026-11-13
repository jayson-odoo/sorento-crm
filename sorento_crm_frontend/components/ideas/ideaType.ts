import type { Idea, IdeaType } from '@/types/ideas';

/** What each submission type reads as on the list, its filter and the detail page. */
export const IDEA_TYPE_LABEL: Record<IdeaType, string> = {
  idea: 'Feature request',
  issue: 'Issue',
};

/** The one read of an idea's type: missing or unknown type data is an idea. */
export function ideaType(idea: Pick<Idea, 'type'>): IdeaType {
  return idea.type === 'issue' ? 'issue' : 'idea';
}
