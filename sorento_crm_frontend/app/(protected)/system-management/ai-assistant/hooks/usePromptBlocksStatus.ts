'use client';

import { useQuery } from '@tanstack/react-query';
import { getPromptBlocksStatus } from '../services/aiPromptsService';

/**
 * The Prompts page's "domain block out of date" banner (chatbot turn re-architecture,
 * AC-1552). Its own hook file, separate from `useAIAssistantPrompts.ts` - that module
 * is wholesale-mocked by `PromptsList.test.tsx` (`vi.mock('../../hooks/
 * useAIAssistantPrompts', () => ({ usePromptKeys: ... }))`), and a second export there
 * would need every existing caller's mock touched to keep working.
 */
export function usePromptBlocksStatus() {
  return useQuery({
    queryKey: ['ai-prompts', 'prompt-blocks-status'],
    queryFn: getPromptBlocksStatus,
  });
}
