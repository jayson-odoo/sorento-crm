import type { CertificateValidity } from '../services/quotationCertificateService';

/** The validity pill of a quoted certificate: one wording and colour on the list and the page. */
export const VALIDITY: Record<
  CertificateValidity,
  { label: string; variant: 'success' | 'warning' | 'destructive' | 'secondary' }
> = {
  valid: { label: 'Valid', variant: 'success' },
  expiring: { label: 'Expiring', variant: 'warning' },
  expired: { label: 'Expired', variant: 'destructive' },
  unknown: { label: 'Unknown', variant: 'secondary' },
};
