/** AC-QTSO-CRM wire shapes: the write routes' answer and the capability read. */

export type AutocountWriteOutcome =
  | 'done'
  | 'refused'
  | 'pending_verification'
  | 'unreachable'
  | 'waiting'
  | (string & {});

export interface AutocountWriteLine {
  line_no: number;
  item_code: string | null;
  description: string | null;
  qty: string;
  unit_price: string;
  location: string | null;
  delivery_date: string | null;
}

export interface AutocountWriteWarning {
  code?: string;
  message?: string;
}

export interface AutocountSkippedLine {
  code: string | null;
  description: string | null;
}

export interface AutocountExplodedSet {
  code: string | null;
  components: { code: string; qty: string }[];
}

export interface AutocountWaitingChange {
  verb?: string | null;
  line_no?: number | null;
  item_code?: string | null;
  reason: string;
}

export interface AutocountWriteResult {
  outcome: AutocountWriteOutcome;
  message: string;
  doc_no: string | null;
  lines: AutocountWriteLine[];
  warnings: (AutocountWriteWarning | string)[];
  skipped: AutocountSkippedLine[];
  exploded: AutocountExplodedSet[];
  waiting: AutocountWaitingChange[];
}

export interface AutocountCapability {
  enabled: boolean;
  reason: string | null;
}

export type AutocountCapabilityMap = Partial<
  Record<'create_doc' | 'edit_doc' | 'add_line' | 'delete_line' | 'cancel_doc', AutocountCapability>
>;

export interface AutocountWriteCapabilities {
  enabled: boolean;
  sales_orders: AutocountCapabilityMap;
  quotations: AutocountCapabilityMap;
}
