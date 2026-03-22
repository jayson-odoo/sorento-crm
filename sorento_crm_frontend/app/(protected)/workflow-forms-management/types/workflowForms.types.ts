export type WorkflowFieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'email'
  | 'date'
  | 'datetime'
  | 'date_range'
  | 'select'
  | 'multi_select'
  | 'checkbox'
  | 'radio'
  | 'url'
  | 'phone';

export interface WorkflowHeaderField {
  id: string;
  type: WorkflowFieldType;
  label: string;
  required?: boolean;
  help_text?: string;
  placeholder?: string;
  options?: { value: string; label: string }[];
}

export interface WorkflowHeaderSection {
  id: string;
  title: string;
  fields: WorkflowHeaderField[];
}

export interface WorkflowLineGroup {
  id: string;
  name: string;
  fields: WorkflowHeaderField[];
}

export interface WorkflowState {
  id: string;
  name: string;
  code: string;
  is_initial?: boolean;
  is_terminal?: boolean;
  view_role_ids?: string[];
  edit_role_ids?: string[];
}

export interface WorkflowTransition {
  id: string;
  from_state_id: string;
  to_state_id: string;
  label: string;
  direction: 'forward' | 'back';
  allowed_role_ids?: string[];
}

export interface WorkflowNotificationRule {
  transition_id: string;
  channels: ('in_app' | 'email')[];
  recipient_role_ids: string[];
}

export interface WorkflowFormSchema {
  /** Preferred: header fields grouped into sections (drag-and-drop in builder). */
  header_sections?: WorkflowHeaderSection[];
  /** Flat list kept in sync for APIs / legacy; use header_sections when present. */
  header_fields: WorkflowHeaderField[];
  line_groups: WorkflowLineGroup[];
  states: WorkflowState[];
  transitions: WorkflowTransition[];
  notification_rules: WorkflowNotificationRule[];
}

export interface WorkflowFormDefinition {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  draft_schema: WorkflowFormSchema;
  published_version_id?: string | null;
  published_version_number?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface WorkflowSubmissionLine {
  id: string;
  line_group_id: string;
  sort_order: number;
  row_data: Record<string, unknown>;
}

export interface WorkflowTransitionLog {
  id: string;
  from_state_code?: string | null;
  to_state_code: string;
  transition_id?: string | null;
  remark?: string | null;
  user_id?: string | null;
  created_at?: string;
}

export interface WorkflowSubmission {
  id: string;
  definition_id: string;
  version_id: string;
  current_state_code: string;
  header_data: Record<string, unknown>;
  lines: WorkflowSubmissionLine[];
  transition_logs: WorkflowTransitionLog[];
  created_at?: string;
  updated_at?: string;
  created_by_user_id?: string | null;
  /** From API when loaded with submission (no definitions.view needed). */
  definition_name?: string | null;
  definition_code?: string | null;
  form_version_number?: number | null;
  form_schema?: WorkflowFormSchema | null;
}

export interface ListPagination {
  total: number;
  page: number;
  limit: number;
}

export interface Paginated<T> {
  data: T[];
  pagination: ListPagination;
  empty: boolean;
}
