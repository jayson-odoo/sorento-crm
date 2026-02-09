import type { AttachmentResponse } from '@/app/(protected)/resource-management/attachments/types/attachment.types';

export interface PromotionAttachment {
  id: string;
  promotion_id: string;
  attachment_id: string;
  is_primary?: boolean | null;
  sort_order?: number | null;
  created_at?: Date | string | null;
  created_by?: string | null;
  synced_to_excel?: boolean | null;
  last_synced_to_excel?: Date | string | null;
  updated_at?: Date | string | null;
  promotion?: {
    id: string;
    promo_code: string;
    name: string;
  };
  attachment?: AttachmentResponse;
}

export interface PromotionAttachmentFormData {
  promotion_id: string;
  attachment_id: string;
  is_primary?: boolean;
  sort_order?: number;
}
