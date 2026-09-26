/**
 * Sales targets as `/api/v1/sales/targets` serialises them (plan 3.1, 3.8, 16.3). Dates are
 * `YYYY-MM-DD` strings, datetimes naive UTC, money and units plain JSON numbers.
 */
export type TargetSubjectKind = 'agent' | 'team';
export type TargetMetric = 'amount' | 'quantity';
export type TargetBasis = 'ordered' | 'delivered';
export type TargetProductScope = 'all' | 'categories' | 'products';
export type TargetSplitUnit = 'day' | 'week' | 'month';

export interface TargetMemberRef {
  sales_agent_id: string;
  /** `ALI - Ali Hassan`: code and name, never an id. */
  label: string;
}

/** One target period containing the list's date, or a "No target" row (target fields null). */
export interface SalesTargetRow {
  target_id: string | null;
  target_no: string | null;
  name: string | null;
  subject_kind: TargetSubjectKind;
  sales_agent_id: string | null;
  sales_team_id: string | null;
  subject_label: string;
  /** Agent rows: the team the agent is in on the date. Team rows: the team. */
  team_id: string | null;
  team_name: string | null;
  /** Agent rows under a team filter: the last day of a stay that ended on or before the date. */
  left_on: string | null;
  /** Team rows: the members on the date. Null on agent rows. */
  members: TargetMemberRef[] | null;
  metric: TargetMetric | null;
  basis: TargetBasis | null;
  product_scope: TargetProductScope | null;
  scope_labels: string[];
  period_id: string | null;
  period_start: string | null;
  period_end: string | null;
  end_date?: string | null;
  target_value: number | null;
  achieved_value: number | null;
  achieved_pct: number | null;
  parent_target_id: string | null;
}

export interface SalesTargetList {
  on: string;
  rows: SalesTargetRow[];
  /** Ordered amount with no agent, in the calendar month of `on`. */
  unassigned_amount: number;
  /** Active agents in no team on `on`. */
  no_team_count: number;
}

export interface SalesTargetListParams {
  on: string;
  subject: TargetSubjectKind;
  /** A team id, or `none` (agents only) for agents in no team. */
  salesTeamId?: string;
  query?: string;
}

export interface SalesTargetPeriod {
  id: string;
  period_start: string;
  period_end: string;
  target_value: number;
  achieved_value: number | null;
  achieved_pct: number | null;
  is_current: boolean;
}

export interface SalesTargetChild {
  target_id: string;
  target_no?: string;
  sales_agent_id: string;
  label: string;
  periods: { id?: string; period_start: string; target_value: number }[];
}

export interface SalesTargetDetail {
  id: string;
  target_no: string;
  name: string;
  subject_kind: TargetSubjectKind;
  sales_agent_id: string | null;
  sales_team_id: string | null;
  subject_label: string;
  /** Agent targets: the team the agent is in today. */
  subject_team_name: string | null;
  parent: { id: string; name: string; target_no?: string } | null;
  metric: TargetMetric;
  basis: TargetBasis;
  product_scope: TargetProductScope;
  start_date: string;
  end_date: string;
  split_every: number | null;
  split_unit: TargetSplitUnit | null;
  /** "Ordered", "Delivered", or "Delivered (by DO date)". */
  counts_label: string;
  /** The categories or products counted, by their own id. */
  scope: { id: string; label: string }[];
  periods: SalesTargetPeriod[];
  children: SalesTargetChild[];
  members_without_figure: TargetMemberRef[];
  child_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface SalesTargetOptions {
  agents: { id: string; code: string; label: string; team_id: string | null; team_name: string | null }[];
  teams: {
    id: string;
    name: string;
    is_active: boolean;
    /** Every stay, so the modal can offer the members overlapping the chosen range. */
    members: { sales_agent_id: string; label: string; valid_from: string | null; valid_to: string | null }[];
  }[];
  categories: { id: string; label: string; parent_category_id: string | null }[];
}

interface TargetCreateBase {
  name: string;
  metric: TargetMetric;
  basis: TargetBasis;
  product_scope: TargetProductScope;
  category_ids?: string[];
  product_ids?: string[];
  start_date: string;
  end_date: string;
  split_every?: number;
  split_unit?: TargetSplitUnit;
}

export interface AgentTargetCreatePayload extends TargetCreateBase {
  subject_kind: 'agent';
  sales_agent_id: string;
  /** Written to every period. */
  target_value: number;
}

export interface TeamTargetCreatePayload extends TargetCreateBase {
  subject_kind: 'team';
  sales_team_id: string;
  /** One child agent target each; the team figure is their sum. */
  agent_figures: { sales_agent_id: string; target_value: number }[];
}

export type SalesTargetCreatePayload = AgentTargetCreatePayload | TeamTargetCreatePayload;

/** The header fields a PATCH may send; `split_every`/`split_unit` null turn the split off. */
export interface SalesTargetUpdatePayload {
  name?: string;
  metric?: TargetMetric;
  basis?: TargetBasis;
  product_scope?: TargetProductScope;
  category_ids?: string[];
  product_ids?: string[];
  start_date?: string;
  end_date?: string;
  split_every?: number | null;
  split_unit?: TargetSplitUnit | null;
}
