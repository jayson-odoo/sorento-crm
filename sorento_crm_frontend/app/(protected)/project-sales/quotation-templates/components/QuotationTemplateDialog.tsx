'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import { useQuotationTemplateMutations } from '../../_shared/hooks/useQuotationTemplates';
import type { QuotationTemplate } from '../../_shared/services/quotationTemplateService';

/** Create or edit one terms template. Editing never touches a quotation already created. */
export function QuotationTemplateDialog({
  template,
  onDone,
}: {
  template: QuotationTemplate | null;
  onDone: () => void;
}) {
  const { create, update } = useQuotationTemplateMutations('terms');
  const [name, setName] = React.useState(template?.name ?? '');
  const [bodyHtml, setBodyHtml] = React.useState(template?.body_html ?? '');
  const [paymentTerms, setPaymentTerms] = React.useState(template?.payment_terms ?? '');
  const [validity, setValidity] = React.useState(template?.validity ?? '');
  const pending = create.isPending || update.isPending;

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92dvh] w-full max-w-2xl overflow-hidden">
        <DialogHeader>
          <DialogTitle>{template ? `Edit ${template.name}` : 'Add a terms template'}</DialogTitle>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const body = {
              name: name.trim(),
              body_html: bodyHtml,
              payment_terms: paymentTerms.trim() || null,
              validity: validity.trim() || null,
            };
            try {
              if (template) {
                await update.mutateAsync({ id: template.id, body });
              } else {
                await create.mutateAsync(body);
              }
              onDone();
            } catch {
              // the mutation already toasted the refusal; keep the dialog open
            }
          }}
        >
          <DialogBody className="max-h-[65dvh] space-y-4 overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="quotation-template-name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="quotation-template-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={150}
                required
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="min-w-0 space-y-1.5">
                <Label htmlFor="quotation-template-payment-terms">Payment Terms</Label>
                <Input
                  id="quotation-template-payment-terms"
                  value={paymentTerms}
                  onChange={(event) => setPaymentTerms(event.target.value)}
                />
              </div>
              <div className="min-w-0 space-y-1.5">
                <Label htmlFor="quotation-template-validity">Validity</Label>
                <Input
                  id="quotation-template-validity"
                  value={validity}
                  onChange={(event) => setValidity(event.target.value)}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>
                Terms and conditions <span className="text-destructive">*</span>
              </Label>
              <RichTextEditor value={bodyHtml} onChange={setBodyHtml} minHeight={260} />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || !bodyHtml.trim() || pending}>
              {template ? 'Save changes' : 'Add template'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
