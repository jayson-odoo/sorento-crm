import type { AttachmentResponse } from '@/app/(protected)/resource-management/attachments/types/attachment.types';

export interface ProductAttachment {
  id: string;
  product_id: string;
  attachment_id: string;
  is_primary?: boolean | null;
  sort_order?: number | null;
  created_at?: Date | string | null;
  created_by?: string | null;
  synced_to_excel?: boolean | null;
  last_synced_to_excel?: Date | string | null;
  updated_at?: Date | string | null;
  product?: {
    id: string;
    product_code: string;
    product_name: string;
  };
  attachment?: AttachmentResponse;
}

export interface ProductAttachmentFormData {
  product_id: string;
  attachment_id: string;
  is_primary?: boolean;
  sort_order?: number;
}
