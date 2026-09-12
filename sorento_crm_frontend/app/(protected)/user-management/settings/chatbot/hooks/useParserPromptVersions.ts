import { useQuery } from '@tanstack/react-query';
import { getConsolePromptVersions } from '@/app/(protected)/system-management/chatbot-console/services/chatbotConsoleService';

// The SAME key the chatbot console's own query uses, so the two screens share one cached
// answer rather than each fetching the parser's version list.
export const PARSER_PROMPT_VERSIONS_KEY = ['chatbot-console', 'prompt-versions'];

/**
 * The `chatbot_semantic_parser` versions, newest first, for the shadow-version select
 * (AC-1028).
 *
 * Reuses the console feature's service rather than adding a second caller of the same
 * endpoint: one reader, one contract, and a change to that response reaches both screens.
 *
 * Its OWN module, not a fourth export of `useChatbotSettings`: it reads a different
 * endpoint, belongs to the prompt registry rather than to the settings row, and the two
 * are mocked separately by anything testing this page.
 */
export function useParserPromptVersions() {
  return useQuery({
    queryKey: PARSER_PROMPT_VERSIONS_KEY,
    queryFn: getConsolePromptVersions,
    staleTime: 60_000,
    retry: 1,
  });
}
