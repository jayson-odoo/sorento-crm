export interface SLAPolicy {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at: Date;
  updated_at: Date;
}

export interface SLAPolicyFormData {
  code: string;
  name: string;
  description?: string;
  is_active: boolean;
}

export interface SLAPolicyDetail extends SLAPolicy {
  tiers_count?: number;
  tiers?: SLAPolicyTier[];
}

export interface SLAPolicyTier {
  id: string;
  policy_id: string;
  tier_level: number;
  tier_name: string;
  // Decimal hours - backend serializes as a string ("0.50"); coerce with Number() to display/compute.
  response_hours: number | string;
  resolution_hours: number | string;
  created_at: Date;
  updated_at: Date;
}

export interface SLAPolicyTierFormData {
  tier_level: number;
  tier_name: string;
  response_hours: number;
  resolution_hours: number;
}
