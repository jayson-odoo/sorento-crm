/**
 * Chatbot Domains (chatbot turn re-architecture, S1 - AC-1510, AC-1511).
 *
 * A domain row replaces one entry of the `DOMAIN_SPEC` Python constant (PLAN
 * "Design > The policy"). The narrowing policy is per (domain, entity kind) - `narrowing`
 * is a map keyed by entity kind code, not a single value - and `ladder` is the ordered
 * list of OTHER domain names this domain escalates to when its own answer is zero or
 * short (contract line 3).
 */

/** Per (domain, entity kind) policy - PLAN "Design > The policy". */
export type NarrowingPolicy =
  | 'must_narrow_one'
  | 'narrow_to_code'
  | 'narrow_by_type'
  | 'narrow_by_tier'
  | 'optional_filter'
  | 'list_all'
  | 'not_applicable';

export const NARROWING_POLICY_OPTIONS: { value: NarrowingPolicy; label: string }[] = [
  { value: 'must_narrow_one', label: 'Must narrow to one' },
  { value: 'narrow_to_code', label: 'Narrow to a code' },
  { value: 'narrow_by_type', label: 'Narrow by type' },
  { value: 'narrow_by_tier', label: 'Narrow by tier' },
  { value: 'optional_filter', label: 'Optional filter' },
  { value: 'list_all', label: 'List all variants' },
  { value: 'not_applicable', label: 'Not applicable' },
];

/**
 * The eight escalation teams (`contracts.SUGGESTED_TEAMS`, backend). A fixed code
 * set, not a row in the `teams` table - UAC ruling 16 Sep 2026. `escalation_team_code`
 * on a domain holds one of these codes.
 */
export const SUGGESTED_TEAM_OPTIONS: { value: string; label: string }[] = [
  { value: 'purchasing', label: 'Purchasing' },
  { value: 'purchasing_certification', label: 'Purchasing (certification)' },
  { value: 'customer_service', label: 'Customer service' },
  { value: 'marketing_product', label: 'Marketing product' },
  { value: 'marketing_form', label: 'Marketing form' },
  { value: 'warehouse', label: 'Warehouse' },
  { value: 'marketing_promotion', label: 'Marketing promotion' },
  { value: 'it_admin', label: 'IT admin' },
];

export interface ChatbotDomain {
  id: string;
  /** The domain key the engine and the parser prompt refer to, e.g. "incoming". */
  name: string;
  /** What the customer sees. */
  label: string;
  intents: string[];
  /** MCP tool names this domain may call. */
  tools: string[];
  primary_tool: string | null;
  /** One of `SUGGESTED_TEAM_OPTIONS`'s codes. Null reads as "no escalation team set yet". */
  escalation_team_code: string | null;
  switch_words: string[];
  /** Entity kind code -> policy. Only kinds present here are narrowed under this domain. */
  narrowing: Record<string, NarrowingPolicy>;
  takes_date_filter: boolean;
  /** Field-reveal key this domain's answer requires, or null. */
  reveal_key: string | null;
  supported: boolean;
  /** Ordered list of domain names to climb when this domain's answer is zero or short. */
  ladder: string[];
  updated_at: string;
}

export type ChatbotDomainInput = Omit<ChatbotDomain, 'id' | 'updated_at'>;
