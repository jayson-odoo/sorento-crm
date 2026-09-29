/** A row of the AutoCount branch table (#1356), read only. */
export interface Branch {
  id: string;
  source_book: string;
  /** AutoCount `AccNo`: the debtor code, `''` when AutoCount sent none. */
  acc_no: string;
  branch_code: string;
  branch_name: string | null;
  last_synced_at: string | null;
  /** The CRM customer whose code matches `acc_no`, when there is one. */
  customer_id: string | null;
  customer_name: string | null;
}
