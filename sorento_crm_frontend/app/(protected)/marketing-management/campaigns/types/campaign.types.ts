export interface CampaignType {
  id: string;
  type_name: string;
  description?: string | null;
}

export interface Campaign {
  id: string;
  campaign_code: string;
  campaign_name: string;
  campaign_type_id: string;
  description?: string | null;
  start_date: Date;
  end_date?: Date | null;
  budget?: number | null;
  target_audience?: string | null;
  status: 'planning' | 'active' | 'completed' | 'cancelled';
  created_at: Date;
  updated_at: Date;
  created_by?: string | null;
  campaign_type?: CampaignType;
  spent?: number;
}

export interface CampaignFormData {
  campaign_code: string;
  campaign_name: string;
  campaign_type_id: string;
  description?: string;
  start_date: Date;
  end_date?: Date | null;
  budget?: number;
  target_audience?: string;
  status: 'planning' | 'active' | 'completed' | 'cancelled';
}

export interface CampaignDetail extends Campaign {
  metrics?: {
    total_impressions: number;
    click_through_rate: number;
    conversion_rate: number;
    revenue_attributed: number;
  };
  budget_tracker?: {
    total_budget: number;
    spent_to_date: number;
    remaining_budget: number;
    progress_percent: number;
    burn_rate: number;
  };
  associated_promotions?: any[];
  campaign_activities?: any[];
  related_orders?: any[];
}
