export interface LinkedEntityRef {
  id: string;
  name: string;
  description?: string | null;
  link_id?: string | null; // ProductAttachment/PromotionAttachment id for unlink; form uses id
  /** Present only on a SHARED attachment's rows - which company the linked row belongs to. */
  company_id?: string | null;
  company_name?: string | null;
  /** True when the row's company is the active company, or the row has no company.
   *  Absent on a single-company attachment, where every row is in scope today. */
  in_scope?: boolean;
}

export interface Attachment {
  id: string;
  attachment_type_id?: string | null;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  file_size_bytes: number | null;
  mime_type: string | null;
  file_hash?: string | null;
  entity_type: string | null;
  entity_id: string | null;
  directory_id?: string | null;
  full_directory_path?: string | null;  // e.g. "SORENTO CABANA (DEALER) --> SORENTO --> Product Photo --> Angle Valve"
  description?: string | null;
  access_levels?: string[] | null;  // e.g. ["dealer", "end_user"]
  entity_display_name?: string | null;
  linked_products?: LinkedEntityRef[];
  linked_promotions?: LinkedEntityRef[];
  linked_form?: LinkedEntityRef | null;
  linked_packing_lists?: LinkedEntityRef[];
  /** Certificates this file is a filed revision of. Read-only: the link
   *  exists because the document was filed, not because a user made it. */
  linked_certificates?: LinkedEntityRef[];
  /** Owning company. Null means the file is shared across every company. */
  company_id?: string | null;
  company_name?: string | null;
  uploaded_by?: string | null;
  uploaded_at: Date;
  created_at: Date;
  is_deleted: boolean;
  deleted_at?: Date | null;
  deleted_by?: string | null;
  virus_status?: 'clean' | 'scanning' | 'infected' | 'unknown';
  uploaded_by_user?: {
    id: string;
    name: string;
    email: string;
  };
  entity_name?: string;
  attachment_type?: AttachmentTypeSimple | null;
  // Field-linkage template chosen at upload time. When the attachment is
  // later linked to a row via any link API, the backend fans this template
  // out into per-row attachment_field_links rows.
  target_entity_type?: FieldLinkageEntityType | null;
  target_field_keys?: string[] | null;
}

export type FieldLinkageEntityType =
  | 'product'
  | 'promotion'
  | 'packing_list'
  | 'form';

export interface AttachmentType {
  id: string;
  type_name: string;
  description?: string | null;
  allowed_extensions: string;
  max_file_size_mb: number;
  /** Max attachments of this type per entity row; null = unlimited. */
  max_count_per_entity?: number | null;
  supports_field_linkage?: boolean;
  /** Cert-bearing signal: an upload of this type can file a certificate. */
  is_certificate?: boolean;
  /** Plausibility ceiling for a certificate's validity span; null = no limit. */
  max_validity_months?: number | null;
  /** When false, uploads skip the n8n intake webhook and the upload-activity drawer. */
  triggers_n8n_webhook?: boolean;
  /** An upload of this type is written with company_id = NULL (visible to every company). */
  is_shared?: boolean;
  created_at: Date;
}

export interface AttachmentTypeSimple {
  id: string;
  type_name: string;
  description?: string | null;
}

// Nested attachment shape returned by product-attachments API (AttachmentSimple)
export interface AttachmentSimple {
  id: string;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  file_size_bytes?: number | null;
  mime_type?: string | null;
  uploaded_at: Date | string;
  created_at?: Date | string;
  attachment_type?: AttachmentTypeSimple | null;
  full_directory_path?: string | null;
  access_levels?: string[] | null;
}

export interface AttachmentResponse {
  id: string;
  attachment_type_id?: string | null;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  /** CDN base URL of the stored grid thumbnail; null for non-images / pre-backfill. */
  thumbnail_path?: string | null;
  /** Freshly-signed thumbnail URL supplied by the drive-list serializer for the grid. */
  thumbnail_url?: string | null;
  file_size_bytes?: number | null;
  mime_type?: string | null;
  file_hash?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  directory_id?: string | null;
  full_directory_path?: string | null;
  description?: string | null;
  access_levels?: string[] | null;
  entity_display_name?: string | null;
  linked_products?: LinkedEntityRef[];
  linked_promotions?: LinkedEntityRef[];
  linked_form?: LinkedEntityRef | null;
  linked_packing_lists?: LinkedEntityRef[];
  /** Certificates this file is a filed revision of. Read-only: the link
   *  exists because the document was filed, not because a user made it. */
  linked_certificates?: LinkedEntityRef[];
  /** Owning company. Null means the file is shared across every company. */
  company_id?: string | null;
  company_name?: string | null;
  uploaded_by?: string | null;
  uploaded_at: Date | string;
  created_at?: Date | string;
  is_deleted: boolean;
  deleted_at?: Date | string | null;
  deleted_by?: string | null;
  attachment_type?: AttachmentTypeSimple | null;
  target_entity_type?: FieldLinkageEntityType | null;
  target_field_keys?: string[] | null;
}

/** What the detail card prints for the owning company. Null company = shared
 *  across every company; a set id with no resolved name never shows the id. */
export function attachmentCompanyLabel(
  attachment: Pick<Attachment, 'company_id' | 'company_name'>,
): string {
  const name = attachment.company_name?.trim();
  if (name) return name;
  return attachment.company_id ? '-' : 'Shared';
}
