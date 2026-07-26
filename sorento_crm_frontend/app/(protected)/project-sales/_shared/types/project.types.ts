/**
 * Project Sales types. Mirrors `app/schemas/projects.py`.
 *
 * Two contract details carry meaning that is easy to lose:
 *
 * - `can_edit` is computed by the SERVER from ownership, collaborator rows and the
 *   manage permission. Never re-derive it in the browser: a second implementation of
 *   the ownership rule is a second place for it to disagree with the API, and the API
 *   is the one that decides.
 * - A clash candidate's `similarity` and `blocks` are independent. A perfect title
 *   match on a lost project is 1.0 and still does not block, because re-tendering is
 *   legitimate. Render the list from `blocks`, never from a similarity threshold.
 */

export type ProjectOutcome = 'open' | 'won' | 'lost' | 'dormant';

export type PartyType =
  | 'developer'
  | 'architect'
  | 'main_contractor'
  | 'trading_house'
  | 'consultant';

export type InfluenceLevel = 'high' | 'medium' | 'low';

export interface ProjectParty {
  id: string;
  party_type: PartyType;
  name: string;
  registration_no?: string | null;
  address?: string | null;
  phone?: string | null;
  email?: string | null;
  notes?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  is_active: boolean;
  project_count?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProjectPartyBody {
  party_type: PartyType;
  name: string;
  registration_no?: string | null;
  address?: string | null;
  phone?: string | null;
  email?: string | null;
  notes?: string | null;
  customer_id?: string | null;
  is_active?: boolean;
}

export interface ProjectTemplateRole {
  id: string;
  name: string;
  sort_order: number;
  is_active: boolean;
}

export interface ProjectType {
  id: string;
  name: string;
  code: string;
  description?: string | null;
  /**
   * Property developments infer a delivery window from launch date plus a
   * configurable lag; every other type has to state the window explicitly, so the
   * registration form switches which fields it requires on this flag.
   */
  derives_delivery_from_launch: boolean;
  sort_order: number;
  is_active: boolean;
  template_count?: number | null;
}

export interface ProjectTemplate {
  id: string;
  type_id: string;
  type_name?: string | null;
  name: string;
  description?: string | null;
  is_active: boolean;
  roles: ProjectTemplateRole[];
  has_forked_status_graph: boolean;
}

export interface Project {
  id: string;
  project_code: string;
  title: string;
  outcome: ProjectOutcome;
  loss_reason?: string | null;

  developer_party_id?: string | null;
  developer_name?: string | null;
  type_id?: string | null;
  type_name?: string | null;
  template_id?: string | null;
  template_name?: string | null;

  status_id?: string | null;
  status_key?: string | null;
  status_label?: string | null;

  owner_user_id?: string | null;
  owner_name?: string | null;

  is_critical: boolean;
  critical_at?: string | null;
  management_support?: string | null;
  management_notes?: string | null;

  registered_company_name?: string | null;
  location?: string | null;
  address?: string | null;
  architect_party_id?: string | null;
  architect_name?: string | null;
  main_contractor_party_id?: string | null;
  main_contractor_name?: string | null;
  estimated_sales_value?: string | null;
  launch_date?: string | null;
  expected_delivery_from?: string | null;
  expected_delivery_to?: string | null;
  brands: string[];
  brand_ids: string[];

  last_meaningful_activity_at?: string | null;
  days_since_last_activity?: number | null;
  can_edit: boolean;

  created_at?: string | null;
  updated_at?: string | null;
}

export interface ProjectRegisterBody {
  title: string;
  developer_party_id?: string | null;
  type_id?: string | null;
  template_id?: string | null;
  owner_user_id?: string | null;
  registered_company_name?: string | null;
  location?: string | null;
  address?: string | null;
  architect_party_id?: string | null;
  main_contractor_party_id?: string | null;
  estimated_sales_value?: string | null;
  launch_date?: string | null;
  expected_delivery_from?: string | null;
  expected_delivery_to?: string | null;
  brand_ids?: string[];
}

export interface ProjectUpdateBody extends Partial<ProjectRegisterBody> {
  is_critical?: boolean;
  management_support?: string | null;
  management_notes?: string | null;
  loss_reason?: string | null;
}

export interface ClashCandidate {
  project_id: string;
  project_code: string;
  title: string;
  outcome: ProjectOutcome;
  status_label?: string | null;
  owner_user_id?: string | null;
  owner_name?: string | null;
  developer_name?: string | null;
  estimated_sales_value?: string | null;
  brands: string[];
  last_activity_at?: string | null;
  similarity: number;
  blocks: boolean;
}

export interface ClashPreview {
  candidates: ClashCandidate[];
  would_block: boolean;
}

export interface ProjectStakeholder {
  id: string;
  project_id: string;
  person_name: string;
  role_id?: string | null;
  role_name?: string | null;
  party_id?: string | null;
  party_name?: string | null;
  job_title?: string | null;
  phone?: string | null;
  email?: string | null;
  influence?: InfluenceLevel | null;
  is_primary: boolean;
  notes?: string | null;
}

export interface ProjectStakeholderBody {
  person_name: string;
  role_id?: string | null;
  party_id?: string | null;
  job_title?: string | null;
  phone?: string | null;
  email?: string | null;
  influence?: InfluenceLevel | null;
  is_primary?: boolean;
  notes?: string | null;
}

export interface TakeoverRequest {
  id: string;
  project_id: string;
  project_code?: string | null;
  project_title?: string | null;
  kind: 'join' | 'dispute';
  reason: string;
  status: 'pending' | 'approved' | 'rejected';
  requester_user_id: string;
  requester_name?: string | null;
  decided_by?: string | null;
  decided_by_name?: string | null;
  decided_at?: string | null;
  decision_note?: string | null;
  created_at?: string | null;
}

export interface ProjectCollaborator {
  project_id: string;
  user_id: string;
  user_name?: string | null;
  granted_by?: string | null;
  granted_at?: string | null;
}

export interface ProjectListParams {
  query?: string;
  status_id?: string[];
  outcome?: string[];
  owner_user_id?: string[];
  developer_party_id?: string[];
  type_id?: string[];
  brand_id?: string[];
  only_critical?: boolean;
  page?: number;
  limit?: number;
  sort?: string;
  dir?: 'asc' | 'desc';
}
