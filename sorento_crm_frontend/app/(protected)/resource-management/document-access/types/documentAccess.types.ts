export interface AccessTypeColumn {
  code: string;
  name: string;
}

export interface PreviewCompany {
  id: string;
  name: string;
}

export type ContactBlock = 'no_access_type' | 'no_company' | 'ambiguous';

export interface PreviewContact {
  id: string;
  name: string | null;
  runs_as: 'contact' | 'staff';
  agent_on: boolean;
  access_types: string[];
  companies: PreviewCompany[];
  blocked: ContactBlock | null;
}

export type RowVerdict =
  | 'reads'
  | 'off'
  | 'staff_only'
  | 'not_ticked'
  | 'no_documents'
  | 'staff_reads'
  | 'not_for_staff'
  | ContactBlock;

export interface RowPreview {
  verdict: RowVerdict;
  reads: number;
  total: number;
  no_shared_code: number;
  other_company: number;
}

export interface DocumentAccessRow {
  id: string;
  type_name: string;
  is_shared: boolean;
  is_direct_access: boolean;
  grant_count: number;
  file_count: number;
  readable_count: number;
  ai_read_staff: boolean;
  ai_read_codes: string[];
  /** Readable documents whose access levels hold the code, per active code. */
  reach: Record<string, number>;
  preview: RowPreview | null;
}

export interface DocumentAccessMatrix {
  access_types: AccessTypeColumn[];
  contact: PreviewContact | null;
  rows: DocumentAccessRow[];
}

export type DocumentVerdict = 'reads' | 'no_shared_code' | 'other_company' | ContactBlock;

export interface DocumentAccessDocument {
  id: string;
  original_filename: string;
  access_levels: string[];
  /** Null for a shared file. */
  company_name: string | null;
  ai_read_status: string | null;
  verdict: DocumentVerdict | null;
}

export interface DocumentAccessDocumentsPage {
  items: DocumentAccessDocument[];
  total: number;
  page: number;
  limit: number;
}
