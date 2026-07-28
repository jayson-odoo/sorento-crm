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
}
