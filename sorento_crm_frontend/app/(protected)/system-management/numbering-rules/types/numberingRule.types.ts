export interface DocumentNumberingRule {
  id: string;
  doc_type: string;
  enabled: boolean;
  prefix_template: string | null;
  number_digits: number;
  next_value: number;
  start_value: number;
  reset_policy: string;
  last_reset_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentNumberingRuleUpdate {
  enabled?: boolean;
  prefix_template?: string | null;
  number_digits?: number;
  next_value?: number;
  start_value?: number;
  reset_policy?: string;
}

export const DOC_TYPE_LABELS: Record<string, string> = {
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
  stock_inquiry: 'Stock Inquiry',
  complaint: 'Complaint',
  external_promotion: 'External Promotion',
  purchase_order_crm_spo: 'Supplier purchase order (SPO, from packing list)',
};

export const RESET_POLICY_OPTIONS = [
  { value: 'none', label: 'Never' },
  { value: 'yearly', label: 'Yearly' },
  { value: 'monthly', label: 'Monthly' },
];
