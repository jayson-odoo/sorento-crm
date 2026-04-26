export type WorkflowDomain = 'lead' | 'quotation' | 'tender' | 'task' | 'order' | 'project';

export interface WorkflowStageRow {
  id: string;
  domain: WorkflowDomain;
  code: string;
  label: string;
  color_hex: string | null;
  description: string | null;
  sort_order: number;
  is_terminal: boolean;
  allows_conversion: boolean | null;
  can_go_back: boolean;
  is_active: boolean;
  is_cancelled: boolean;
  created_at: string;
  updated_at: string;
}

export type WorkflowStageUpdatePayload = Partial<
  Pick<
    WorkflowStageRow,
    | 'label'
    | 'color_hex'
    | 'description'
    | 'sort_order'
    | 'is_terminal'
    | 'allows_conversion'
    | 'can_go_back'
    | 'is_active'
    | 'is_cancelled'
  >
>;

export interface WorkflowStageCreatePayload {
  domain: WorkflowDomain;
  code: string;
  label: string;
  color_hex?: string | null;
  description?: string | null;
  sort_order: number;
  is_terminal: boolean;
  allows_conversion: boolean | null;
  can_go_back: boolean;
  is_active: boolean;
  is_cancelled: boolean;
}
