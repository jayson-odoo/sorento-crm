import type { AttachmentType } from '../../attachments/types/attachment.types';

export type { AttachmentType };

export interface AttachmentTypeFormData {
  type_name: string;
  description?: string;
  allowed_extensions: string;
  max_file_size_mb: number;
}
