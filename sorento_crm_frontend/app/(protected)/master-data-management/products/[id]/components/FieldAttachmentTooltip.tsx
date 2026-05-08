'use client';

/**
 * FieldAttachmentTooltip — paperclip popover next to a Specifications field
 * that has at least one linked doc. Shows:
 *   - filename(s) of linked doc(s) with an inline preview link.
 *   - "AI Extract" button that opens AIExtractFieldDialog against the doc and
 *     the (possibly composite) field_keys this trigger is responsible for.
 *
 * Accepts an array of field_keys so the Dimensions trigger can pass three
 * keys at once and the extract dialog returns three values.
 */
import { useMemo, useState } from 'react';
import { Paperclip, Sparkles, Eye } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { getAttachmentPreviewUrl } from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import AIExtractFieldDialog from './AIExtractFieldDialog';
import type { ProductFieldAttachment } from '../../types/product.types';

interface Props {
  productId: string;
  /** One or more field keys this tooltip covers. For composite fields like
   *  Dimensions (L × W × H) pass all three keys; the AI extract dialog will
   *  show three review rows. */
  fieldKeys: string[];
  fieldLabel: string;
  /** Map of {field_key: attachments[]} for this product. */
  fieldAttachments: Record<string, ProductFieldAttachment[]> | null | undefined;
}

export default function FieldAttachmentTooltip({
  productId,
  fieldKeys,
  fieldLabel,
  fieldAttachments,
}: Props) {
  const [extractOpen, setExtractOpen] = useState(false);

  const docs = useMemo(() => {
    if (!fieldAttachments) return [] as ProductFieldAttachment[];
    const seen = new Set<string>();
    const out: ProductFieldAttachment[] = [];
    for (const key of fieldKeys) {
      for (const att of fieldAttachments[key] ?? []) {
        if (seen.has(att.id)) continue;
        seen.add(att.id);
        out.push(att);
      }
    }
    return out;
  }, [fieldAttachments, fieldKeys]);

  if (docs.length === 0) return null;

  // For now the AI extract dialog runs against the FIRST linked doc only.
  // 99% of cases have a single canonical spec sheet per field; if more are
  // linked the user can choose by clicking the doc preview and falling back
  // to the form's own AI Extract.
  const primary = docs[0];

  const handlePreview = async (attachmentId: string) => {
    try {
      const url = await getAttachmentPreviewUrl(attachmentId);
      if (url) window.open(url, '_blank');
    } catch {
      // silent — user can still trigger AI Extract.
    }
  };

  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 ml-1"
            aria-label={`${fieldLabel}: ${docs.length} linked doc${
              docs.length === 1 ? '' : 's'
            }`}
            data-testid={`field-attachment-trigger-${fieldKeys.join('-')}`}
          >
            <Paperclip className="size-3.5 text-primary" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-80"
          data-testid={`field-attachment-popover-${fieldKeys.join('-')}`}
        >
          <div className="space-y-3">
            <div>
              <p className="text-xs text-muted-foreground">Linked to</p>
              <p className="text-sm font-medium">{fieldLabel}</p>
            </div>
            <ul className="space-y-2">
              {docs.map((d) => (
                <li
                  key={d.id}
                  className="flex items-center gap-2 rounded-md border p-2"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" title={d.original_filename}>
                      {d.original_filename}
                    </p>
                    {d.attachment_type?.type_name && (
                      <p className="text-xs text-muted-foreground">
                        {d.attachment_type.type_name}
                      </p>
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => handlePreview(d.id)}
                    aria-label="Preview"
                  >
                    <Eye className="size-4" />
                  </Button>
                </li>
              ))}
            </ul>
            <Button
              type="button"
              size="sm"
              className="w-full"
              onClick={() => setExtractOpen(true)}
              data-testid={`field-attachment-ai-extract-${fieldKeys.join('-')}`}
            >
              <Sparkles className="size-4 mr-2" />
              AI Extract
            </Button>
          </div>
        </PopoverContent>
      </Popover>
      <AIExtractFieldDialog
        open={extractOpen}
        onOpenChange={setExtractOpen}
        productId={productId}
        attachmentId={primary.id}
        fieldKeys={fieldKeys}
      />
    </>
  );
}
