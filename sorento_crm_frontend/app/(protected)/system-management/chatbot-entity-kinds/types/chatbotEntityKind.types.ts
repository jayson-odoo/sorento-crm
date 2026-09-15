import type { NarrowingPolicy } from '@/app/(protected)/system-management/chatbot-domains/types/chatbotDomain.types';

/**
 * Chatbot Entity kinds (chatbot turn re-architecture, S1 - AC-1512).
 *
 * Twelve named kinds today live as a code constant (contract line 19); this is the
 * table that replaces it. `did_you_mean`, `default_narrowing` and `base_property_words`
 * are exactly the three things the 15 Sep "is it discon?" defect traced back to a word
 * list nobody could see (PLAN, M3's `why` note).
 */

export interface ChatbotEntityKind {
  /** The kind code the resolver and the parser prompt refer to, e.g. "product". */
  code: string;
  label: string;
  /** What this kind resolves against, in the reader's words. */
  resolved_against: string;
  did_you_mean: boolean;
  default_narrowing: NarrowingPolicy;
  /** How a family match groups rows, e.g. "by base code". Null when not applicable. */
  family_grouping: string | null;
  /** Product-only: words the parser reads as asking about a property, not a domain. */
  base_property_words: string[];
  updated_at: string;
}

export type ChatbotEntityKindInput = Omit<ChatbotEntityKind, 'updated_at'>;
