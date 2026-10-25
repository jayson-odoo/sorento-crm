/**
 * Project registration from the portal (PROJECT-REG-PORTAL). Names are the API contract in
 * documentation/plans/projects/PLAN-project-registration-portal-25oct.md.
 */

export type ProjectRegistrationStatus = 'draft' | 'pending' | 'approved' | 'rejected';

/** An existing project that looks like the registration; the CRM links to it. */
export interface ProjectRegistrationDuplicate {
  project_id: string;
  project_code: string;
  title: string;
}

export interface ProjectRegistrationRow {
  id: string;
  submitted_at: string | null;
  title: string;
  developer_name: string | null;
  state: string | null;
  sales_agent_name: string | null;
  status: ProjectRegistrationStatus;
  possible_duplicates: ProjectRegistrationDuplicate[];
  project_id: string | null;
  project_code: string | null;
}

/** The parties and type the server matched from the typed names; null when none matched. */
export interface ProjectRegistrationPrefill {
  developer_party_id: string | null;
  architect_party_id: string | null;
  main_contractor_party_id: string | null;
  type_id: string | null;
}

export interface ProjectRegistrationDetail {
  id: string;
  status: ProjectRegistrationStatus;
  reject_reason: string | null;
  submitted_at: string | null;
  decided_at: string | null;
  decided_by_name: string | null;
  /** The CRM user linked to the portal contact, if any. */
  applicant_user_id: string | null;
  project_id: string | null;
  project_code: string | null;

  title: string;
  distributor_name: string | null;
  customer_id: string | null;
  customer_name: string | null;
  type_of_building: string | null;
  state: string | null;
  mukim: string | null;
  your_ref: string | null;
  developer_name: string | null;
  main_contractor_name: string | null;
  architect_name: string | null;
  sales_agent_name: string | null;

  possible_duplicates: ProjectRegistrationDuplicate[];
  prefill: ProjectRegistrationPrefill;
}

export interface ProjectRegistrationPage {
  data: ProjectRegistrationRow[];
  pagination: { total: number; page: number; limit: number };
}
