export interface ConfigStageRow {
  stage_code: string;
  stage_name: string;
  description?: string | null;
  sort_order: number;
  is_terminal: boolean;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ConfigStageFormData {
  stage_code: string;
  stage_name: string;
  description?: string;
  sort_order: number;
  is_terminal: boolean;
  is_active: boolean;
}
