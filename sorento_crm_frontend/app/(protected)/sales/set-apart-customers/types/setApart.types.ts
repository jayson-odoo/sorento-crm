/** Set-apart customers as `/api/v1/sales/set-apart-customers` serialises them. Months are `YYYY-MM`. */
export interface SetApartRow {
  id: string;
  customer_id: string;
  /** The customer's debtor code. */
  debtor_code: string | null;
  customer_name: string | null;
  from_month: string;
  /** Null = still set apart. */
  to_month: string | null;
}

export interface SetApartListResponse {
  data: SetApartRow[];
  pagination: { total: number; page: number; limit: number };
}

export interface SetApartCustomerOption {
  value: string;
  label: string;
}

export interface SetApartSavePayload {
  customer_id: string;
  from_month: string;
  to_month: string | null;
}

export interface SetApartListParams {
  pageIndex: number;
  pageSize: number;
  sorting: { id: string; desc: boolean }[];
  searchQuery: string;
}
