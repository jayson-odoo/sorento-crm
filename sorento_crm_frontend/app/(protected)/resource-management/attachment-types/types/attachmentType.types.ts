import type { AttachmentType } from '../../attachments/types/attachment.types';

export type { AttachmentType };

export interface AttachmentTypeFormData {
  type_name: string;
  description?: string;
  allowed_extensions: string;
  max_file_size_mb: number;
  /** Max attachments of this type per entity row; null = unlimited. */
  max_count_per_entity?: number | null;
  supports_field_linkage?: boolean;
  /** Cert-bearing signal: gates whether an upload also files a certificate. */
  is_certificate?: boolean;
  /** Plausibility ceiling for a certificate's validity span; null = no limit. */
  max_validity_months?: number | null;
}
