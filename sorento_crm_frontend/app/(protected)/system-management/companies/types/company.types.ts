/**
 * Multi-company isolation - frontend types (Phase 1 prototype).
 *
 * `company` is a data-partition dimension below tenant (Sorento + Mocha share
 * one deployment). See documentation/plans/PLAN-multi-company-isolation.md §16.
 */

export type SalesAgentSource = 'document' | 'customer';

export const SALES_AGENT_SOURCE_OPTIONS: { value: SalesAgentSource; label: string }[] = [
  { value: 'document', label: "Document's agent" },
  { value: 'customer', label: "Customer's agent" },
];

export interface Company {
  id: string;
  name: string;
  code: string;
  is_active: boolean;
  /** AutoCount sales-order feed connected for this company. */
  so_feed_live: boolean;
  /** Whose agent a sale belongs to: the document's, or the customer's. */
  sales_agent_source?: SalesAgentSource;
  /** AutoCount company reference (optional). */
  autocount_ref?: string | null;
  logo_url?: string | null;
  created_at?: string | null;
  /** Derived counts for the admin list (users granted / contacts tagged). */
  user_count?: number;
  contact_count?: number;
}

export interface CompanyFormData {
  name: string;
  code: string;
  is_active: boolean;
  /** AutoCount sales-order feed connected for this company. */
  so_feed_live: boolean;
  sales_agent_source: SalesAgentSource;
  autocount_ref?: string | null;
  logo_url?: string | null;
}

/** A user granted the ability to switch into a company (prototypes `user_companies`). */
export interface CompanyUser {
  id: string;
  name: string | null;
  email: string;
}

/** A respond contact tagged to a company (prototypes `respond_contact_companies`). */
export interface CompanyContact {
  id: string;
  name: string;
  phone: string;
}

/** Current user's switchable companies + active/last-active (GET /companies/my-context). */
export interface MyCompanyContext {
  companies: Company[];
  active_company_id: string | null;
  last_active_company_id: string | null;
}
