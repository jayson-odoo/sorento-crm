export interface CustomerGroup {
  id: string;
  name: string;
  ledger_count: number;
  /** Sorted distinct account levels of the member ledgers. */
  account_levels: number[];
  created_at?: string | null;
  updated_at?: string | null;
}

/** A member ledger row (`CustomerResponse`, the fields the Ledgers tab reads). */
export interface GroupLedger {
  id: string;
  customer_code: string;
  customer_name: string;
  account_level?: number | null;
  is_active: boolean;
}

export interface CustomerGroupSelectOption {
  id: string;
  name: string;
  ledger_count: number;
}
