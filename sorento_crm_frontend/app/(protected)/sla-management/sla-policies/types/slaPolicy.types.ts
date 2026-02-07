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
  response_hours: number;
  resolution_hours: number;
  created_at: Date;
  updated_at: Date;
}

export interface SLAPolicyTierFormData {
  tier_level: number;
  tier_name: string;
  response_hours: number;
  resolution_hours: number;
}
