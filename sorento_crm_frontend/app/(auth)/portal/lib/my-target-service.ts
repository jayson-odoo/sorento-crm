/**
 * The portal's My target panel (fix lane round 2, F2): the logging agent's own active targets,
 * from `GET /api/v1/public/portal/sales-opportunities/my-targets`.
 */
import { portalFetch, unwrap } from './portal-client';

export interface MyTargetOpportunity {
  id: string;
  opportunity_no: string;
  title: string;
  customer_or_prospect: string | null;
  stage_label: string | null;
  expected_close_date: string;
  /** What it adds if won: its expected amount, or its lines' quantity on a quantity target. */
  value: string | number;
}

export interface MyTarget {
  target_id: string;
  target_no: string;
  name: string;
  metric: 'amount' | 'quantity' | string;
  basis: string;
  counts_label: string;
  product_scope: string;
  scope_labels: string[];
  start_date: string;
  end_date: string;
  target_value: string | number;
  achieved_value: string | number;
  gap_value: string | number;
  pipeline_value: string | number;
  projected_value: string | number;
  short_value: string | number;
  opportunities: MyTargetOpportunity[];
}

export interface MyTargets {
  today: string;
  targets: MyTarget[];
}

export async function getMyTargets(): Promise<MyTargets> {
  const res = await portalFetch('/api/v1/public/portal/sales-opportunities/my-targets');
  return unwrap<MyTargets>(res, 'Failed to load your targets.');
}
