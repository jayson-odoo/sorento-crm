/** CERT-LINK-CLEANUP: one certificate-product link with its text-check verdict. */
export type CertificateLinkVerdict = 'found' | 'check' | 'not_found' | 'scanned' | 'no_file' | 'pending';

export interface CertificateLink {
  id: string;
  certificate_id: string;
  scheme: string;
  certificate_number: string;
  certificate_type: string | null;
  certificate_status: string;
  product_id: string;
  product_code: string;
  product_name: string | null;
  model_code: string | null;
  model_code_source: 'ai' | 'manual' | null;
  source: 'ai' | 'manual';
  verdict: CertificateLinkVerdict;
  check_code: string | null;
  checked_at: string | null;
}

export type CertificateLinkSummary = Record<CertificateLinkVerdict, number>;

export interface CertificateLinksResponse {
  data: CertificateLink[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
  summary: CertificateLinkSummary;
}
