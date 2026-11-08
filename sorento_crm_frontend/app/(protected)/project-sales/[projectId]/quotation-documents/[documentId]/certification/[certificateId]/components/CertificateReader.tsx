'use client';

import * as React from 'react';
import { Pencil, Trash2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { PdfViewer } from '@/components/common/PdfViewer';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { BoxOverlay } from '@/components/common/pdf-viewer/BoxOverlay';
import { expandBoxesForDefault, type PageBox } from '@/components/common/pdf-viewer/box-geometry';
import { CoverageCodeEditor } from '@/app/(protected)/master-data-management/certificates/components/CoverageCodeEditor';

import { formatDateInMalaysia } from '@/lib/helpers';
import { VALIDITY } from '../../../../../../_shared/lib/quotationCertificateDisplay';
import { projectCrumbs } from '../../../../../../_shared/lib/crumbs';
import {
  quotationCertificateKey,
  useQuotationCertificate,
  useQuotationCertificateMutations,
} from '../../../../../../_shared/hooks/useQuotationCertificates';
import {
  fetchQuotationCertificateFile,
  type BoxScope,
  type CertificateProductDetail,
  type ProductState,
} from '../../../../../../_shared/services/quotationCertificateService';
import { useQueryClient } from '@tanstack/react-query';

const STATE_BADGE: Record<ProductState, { label: string; variant: 'success' | 'warning' | 'secondary' | 'destructive' }> = {
  found: { label: 'Found', variant: 'success' },
  suggested: { label: 'Suggested, check', variant: 'warning' },
  edited: { label: 'Edited', variant: 'secondary' },
  not_found: { label: 'Not found', variant: 'destructive' },
  no_text: { label: 'No text', variant: 'secondary' },
  code_needed: { label: 'Code needed', variant: 'warning' },
};

function ProductRow({
  product,
  certificateId,
  canEditCodes,
  onSaved,
}: {
  product: CertificateProductDetail;
  certificateId: string;
  canEditCodes: boolean;
  onSaved: () => void;
}) {
  const badge = STATE_BADGE[product.state];
  return (
    <li className="flex flex-col gap-1.5 border-b border-border py-2 last:border-b-0">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium" title={product.product_code}>
          {product.product_code}
        </span>
        <Badge variant={badge.variant} appearance="light" size="sm" className="shrink-0">
          {badge.label}
        </Badge>
      </div>
      <div className="flex flex-col gap-0.5 text-sm">
        <span className="text-xs text-muted-foreground">Code on certificate</span>
        <CoverageCodeEditor
          certificateId={certificateId}
          coverageId={product.coverage_id}
          code={product.model_code}
          source={product.model_code_source}
          canEdit={canEditCodes}
          onSaved={onSaved}
        />
      </div>
      {product.number_only && (
        <Badge variant="warning" appearance="light" size="sm" className="w-fit">
          Number only
        </Badge>
      )}
    </li>
  );
}

/**
 * One certificate of a quotation: the PDF with its boxes on the left, the covered products and the
 * save controls on the right. Boxes are fractions of the page, edited locally and saved in one PUT.
 */
export function CertificateReader({
  projectId,
  documentId,
  certificateId,
}: {
  projectId: string;
  documentId: string;
  certificateId: string;
}) {
  const queryClient = useQueryClient();
  const query = useQuotationCertificate(projectId, documentId, certificateId);
  const { saveBoxes, resetBoxes, setSend } = useQuotationCertificateMutations(projectId, documentId);
  const detail = query.data;

  const [boxes, setBoxes] = React.useState<PageBox[]>([]);
  const [dirty, setDirty] = React.useState(false);
  const [selected, setSelected] = React.useState<number | null>(null);
  const [drawing, setDrawing] = React.useState(false);
  const [scope, setScope] = React.useState<BoxScope>('quote');
  const [drawProduct, setDrawProduct] = React.useState('');

  // The server's boxes win whenever they arrive and nothing local is unsaved.
  React.useEffect(() => {
    if (detail && !dirty) {
      setBoxes(detail.boxes);
      setSelected(null);
    }
  }, [detail, dirty]);

  const canEdit = Boolean(detail?.can_edit);
  const canDefaults = Boolean(detail?.can_edit_defaults);
  const productId = drawProduct || detail?.products[0]?.product_id || null;

  const change = React.useCallback((next: PageBox[]) => {
    setBoxes(next);
    setDirty(true);
  }, []);

  const removeAt = React.useCallback(
    (index: number) => {
      change(boxes.filter((_, i) => i !== index));
      setSelected(null);
    },
    [boxes, change],
  );

  // Delete removes the selected box, unless the keys are going into a field.
  React.useEffect(() => {
    if (selected === null || !canEdit) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault();
        removeAt(selected);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [selected, canEdit, removeAt]);

  const loadData = React.useCallback(
    () => fetchQuotationCertificateFile(projectId, documentId, certificateId),
    [projectId, documentId, certificateId],
  );

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: quotationCertificateKey(documentId, certificateId) });

  const save = () => {
    if (!detail) return;
    const payload = scope === 'default' ? expandBoxesForDefault(boxes, productId) : boxes;
    saveBoxes.mutate(
      { certificateId, scope, boxes: payload },
      { onSuccess: () => setDirty(false) },
    );
  };

  const listHref = `/project-sales/${projectId}/quotation-documents/${documentId}/certification`;

  if (query.isLoading) {
    return <Skeleton className="h-[60dvh] w-full" role="status" aria-busy="true" aria-label="Loading" />;
  }
  if (query.error || !detail) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {query.error instanceof Error ? query.error.message : 'Could not load the certificate'}
      </p>
    );
  }

  const title = `${detail.scheme} ${detail.certificate_number}`;
  const alsoFiledAsText = `Also filed as ${detail.also_filed_as
    .map((o) => `${o.scheme} ${o.certificate_number}`)
    .join(', ')}`;
  const productOptions = detail.products.map((p) => ({ value: p.product_id, label: p.product_code }));

  return (
    <div className="flex min-w-0 flex-col gap-3" data-testid="certificate-reader">
      <PageHeader
        title={title}
        crumbs={projectCrumbs(
          projectId,
          { tab: 'quotations' },
          { title: 'Certification', path: listHref },
          { title: detail.certificate_number },
        )}
        titleClassName="truncate"
        actions={<BackToList listPath={listHref} label="Back to certification" appendListState={false} />}
      />

      <div className="grid min-w-0 gap-3 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="flex min-w-0 flex-col gap-2">
          {canEdit && (
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant={drawing ? 'primary' : 'outline'}
                aria-pressed={drawing}
                onClick={() => setDrawing((v) => !v)}
              >
                <Pencil className="size-4" aria-hidden />
                Draw box
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={selected === null}
                onClick={() => selected !== null && removeAt(selected)}
              >
                <Trash2 className="size-4" aria-hidden />
                Remove box
              </Button>
              {drawing && scope === 'default' && productOptions.length > 1 && (
                <SearchableSelect
                  value={productId ?? ''}
                  onChange={setDrawProduct}
                  options={productOptions}
                  placeholder="Product"
                  size="sm"
                  triggerClassName="w-48"
                />
              )}
            </div>
          )}
          <div className="h-[70dvh] min-h-96 overflow-hidden rounded-md border border-border">
            <PdfViewer
              url={null}
              loadData={loadData}
              documentKey={detail.revision_id}
              fileName={`${title}.pdf`}
              title={title}
              pageCountHint={detail.page_count}
              className="h-full"
              unavailable={<p className="p-4 text-sm">No file on this certificate</p>}
              renderPageOverlay={(pageNumber) => (
                <BoxOverlay
                  pageNumber={pageNumber}
                  boxes={boxes}
                  editable={canEdit}
                  drawing={drawing}
                  selected={selected}
                  drawProductId={scope === 'default' ? productId : null}
                  onSelect={setSelected}
                  onChange={change}
                  onRemove={removeAt}
                />
              )}
            />
          </div>
        </div>

        <aside className="flex min-w-0 flex-col gap-4 rounded-md border border-border p-3" aria-label="Products">
          <div className="flex flex-wrap items-center gap-1.5">
            {detail.certifying_body && <Badge variant="secondary" appearance="light" size="sm">{detail.certifying_body}</Badge>}
            <Badge
              variant={VALIDITY[detail.validity_state].variant}
              appearance="light"
              size="sm"
            >
              {VALIDITY[detail.validity_state].label}
              {detail.valid_until ? ` ${formatDateInMalaysia(detail.valid_until)}` : ''}
            </Badge>
            {detail.also_filed_as.length > 0 && (
              <span
                className="text-xs text-muted-foreground"
                title={alsoFiledAsText}
              >
                {alsoFiledAsText}
              </span>
            )}
            {!detail.has_text && detail.has_file && (
              <Badge variant="secondary" appearance="light" size="sm">No text, draw the box</Badge>
            )}
          </div>

          <ul>
            {detail.products.map((p) => (
              <ProductRow
                key={p.coverage_id}
                product={p}
                certificateId={certificateId}
                canEditCodes={canDefaults}
                onSaved={refresh}
              />
            ))}
          </ul>

          {canEdit && (
            <>
              <div className="flex flex-col gap-1.5">
                <Label>Save for</Label>
                <ToggleGroup
                  type="single"
                  variant="outline"
                  size="sm"
                  value={scope}
                  onValueChange={(value) => value && setScope(value as BoxScope)}
                  aria-label="Save for"
                >
                  <ToggleGroupItem value="quote">This quote only</ToggleGroupItem>
                  <ToggleGroupItem value="default" disabled={!canDefaults}>
                    Every quote (this product)
                  </ToggleGroupItem>
                </ToggleGroup>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" disabled={!dirty || saveBoxes.isPending} onClick={save}>
                  Save boxes
                </Button>
                {detail.box_source === 'quote' && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={resetBoxes.isPending}
                    onClick={() =>
                      resetBoxes.mutate(certificateId, { onSuccess: () => setDirty(false) })
                    }
                  >
                    Use default boxes
                  </Button>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="include-in-pdf"
                  checked={detail.send_to_customer}
                  onCheckedChange={(checked) =>
                    setSend.mutate({ certificateId, value: checked === true })
                  }
                />
                <Label htmlFor="include-in-pdf">Include in the certificates PDF</Label>
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
