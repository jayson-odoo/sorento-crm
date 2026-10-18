'use client';

/**
 * The paper sheet of a new product application (NEW-PRODUCT-APP v4, AC-NPA-79), shared by the
 * staff form and detail and the portal form and view so the four cannot drift. Bordered
 * label / value rows in the paper's order; the label stacks above its value under 640 px.
 *
 * Controlled: `value` is the form state, `onChange` hands back the next one. `readOnly` turns
 * every input off (view and edit are the same layout). The sheet owns no network: image
 * changes on a SAVED product go through `imageActions`, and without them a picked file is staged
 * on the product and the host uploads it right after the create returns line ids.
 */

import { useRef, useState, type ReactNode } from 'react';
import { Plus, X } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NumberInput } from '@/components/ui/number-input';
import { Textarea } from '@/components/ui/textarea';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  blankLine,
  type DraftLine,
  type FormState,
} from '@/lib/new-product-application-form';
import type {
  NewProductApplicationImage,
  NewProductApplicationInquiryImage,
} from '@/types/newProductApplication';

export type LookupFetcher = (
  query: string,
  pageIndex: number,
) => Promise<SearchableSelectOption[]>;

/** Image changes on a saved product; the host runs them and refreshes the state. */
export interface SheetImageActions {
  upload: (line: DraftLine, file: File) => Promise<void> | void;
  copy: (line: DraftLine, attachmentId: string) => Promise<void> | void;
  /** The inquiry the SAVED application points at; "Copy from the inquiry" is hidden while another one is picked and unsaved. */
  savedInquiryId: string;
  /** Images on the given inquiry. Null when the list could not be read (the host has said why); never an empty list then. */
  listInquiry: (
    inquiryId: string,
  ) => Promise<NewProductApplicationInquiryImage[] | null>;
}

export interface NewProductApplicationSheetProps {
  value: FormState;
  onChange: (next: FormState) => void;
  applicationNo?: string | null;
  createdAt?: string | null;
  salesPerson?: string | null;
  readOnly?: boolean;
  stockInquiryField?: ReactNode;
  customerField?: ReactNode;
  brands: LookupFetcher;
  /** Keys are `expected_qty_<line key>` plus `lines`. */
  errors?: Record<string, string>;
  /** The staff OPENED AS row and the "From AutoCount" line of one product. */
  lineFooter?: (line: DraftLine, index: number) => ReactNode;
  imageActions?: SheetImageActions;
  /** PURCHASING FEEDBACK: editable in place for purchasing on Approved / Completed. */
  feedback?: { editable: boolean; onSave?: () => void; saving?: boolean };
}

const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp';
const IMAGE_MIME = IMAGE_ACCEPT.split(',');
const NOT_AN_IMAGE = 'Upload a JPEG, PNG or WebP image.';

function Row({
  label,
  required,
  caption,
  children,
}: {
  label: string;
  required?: boolean;
  caption?: string;
  children: ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 border-b last:border-b-0 sm:grid-cols-[11rem_minmax(0,1fr)]">
      <div className="bg-muted/40 px-3 py-2 text-xs font-semibold tracking-wide sm:text-right">
        <div>
          {label}
          {required && <span className="text-destructive"> *</span>}
        </div>
        {caption && (
          <div className="font-normal text-muted-foreground">{caption}</div>
        )}
      </div>
      <div className="min-w-0 break-words px-3 py-2 text-sm">{children}</div>
    </div>
  );
}

function ImageCell({
  line,
  copyEnabled,
  inquiryId,
  readOnly,
  imageActions,
  onStage,
  onStageCopy,
  onRemoveSaved,
}: {
  line: DraftLine;
  copyEnabled: boolean;
  /** The inquiry the picker reads: the saved one for a saved product, the picked one otherwise. */
  inquiryId: string;
  readOnly?: boolean;
  imageActions?: SheetImageActions;
  onStage: (files: File[]) => void;
  onStageCopy: (copies: DraftLine['staged_copies']) => void;
  onRemoveSaved: (image: NewProductApplicationImage) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [picking, setPicking] = useState(false);
  const [offers, setOffers] = useState<NewProductApplicationInquiryImage[]>([]);
  const live = Boolean(line.id && imageActions);

  const choose = (files: FileList | null) => {
    const all = Array.from(files ?? []);
    if (input.current) input.current.value = '';
    const picked = all.filter((f) => IMAGE_MIME.includes(f.type));
    if (picked.length < all.length) toast.error(NOT_AN_IMAGE);
    if (picked.length === 0) return;
    if (live) picked.forEach((f) => void imageActions?.upload(line, f));
    else onStage([...line.staged_images, ...picked]);
  };

  const togglePicker = async () => {
    if (picking) return setPicking(false);
    const found = (await imageActions?.listInquiry(inquiryId)) ?? null;
    if (found === null) return;
    setOffers(found);
    setPicking(true);
  };

  return (
    <div className="space-y-2">
      {line.images.map((image) => (
        <div key={image.link_id} className="flex min-w-0 items-center gap-2">
          <img
            src={image.url}
            alt=""
            className="size-12 shrink-0 rounded border object-cover"
          />
          <a
            href={image.url}
            target="_blank"
            rel="noreferrer"
            className="min-w-0 truncate text-primary hover:underline"
            title={image.filename}
          >
            {image.filename}
          </a>
          {!readOnly && live && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label={`Remove ${image.filename}`}
              onClick={() => onRemoveSaved(image)}
            >
              <X className="size-4" />
            </Button>
          )}
        </div>
      ))}
      {line.staged_images.map((file, i) => (
        <div
          key={`${file.name}-${i}`}
          className="flex min-w-0 items-center gap-2"
        >
          <span className="min-w-0 truncate" title={file.name}>
            {file.name}
          </span>
          {!readOnly && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label={`Remove ${file.name}`}
              onClick={() =>
                onStage(line.staged_images.filter((_, n) => n !== i))
              }
            >
              <X className="size-4" />
            </Button>
          )}
        </div>
      ))}
      {line.staged_copies.map((copy) => (
        <div
          key={copy.attachment_id}
          className="flex min-w-0 items-center gap-2"
        >
          <span className="min-w-0 truncate" title={copy.filename}>
            {copy.filename}
          </span>
          {!readOnly && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label={`Remove ${copy.filename}`}
              onClick={() =>
                onStageCopy(
                  line.staged_copies.filter(
                    (c) => c.attachment_id !== copy.attachment_id,
                  ),
                )
              }
            >
              <X className="size-4" />
            </Button>
          )}
        </div>
      ))}
      {line.images.length === 0 &&
        line.staged_images.length === 0 &&
        line.staged_copies.length === 0 && (
          <span className="text-muted-foreground">-</span>
        )}
      {!readOnly && (
        <div className="flex flex-wrap gap-2">
          <input
            ref={input}
            type="file"
            accept={IMAGE_ACCEPT}
            multiple
            hidden
            aria-label="Add image"
            onChange={(e) => choose(e.target.files)}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => input.current?.click()}
          >
            Add image
          </Button>
          {copyEnabled && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void togglePicker()}
            >
              Copy from the inquiry
            </Button>
          )}
        </div>
      )}
      {picking && (
        <div className="space-y-1 rounded border p-2">
          {offers.length === 0 && (
            <p className="text-muted-foreground">No images on the inquiry.</p>
          )}
          {offers.map((offer) => (
            <button
              key={offer.attachment_id}
              type="button"
              className="block w-full truncate text-left text-primary hover:underline"
              onClick={() => {
                setPicking(false);
                if (live) void imageActions?.copy(line, offer.attachment_id);
                else if (
                  !line.staged_copies.some(
                    (c) => c.attachment_id === offer.attachment_id,
                  )
                )
                  onStageCopy([
                    ...line.staged_copies,
                    {
                      attachment_id: offer.attachment_id,
                      filename: offer.filename,
                    },
                  ]);
              }}
            >
              {offer.filename}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function NewProductApplicationSheet({
  value,
  onChange,
  applicationNo,
  createdAt,
  salesPerson,
  readOnly,
  stockInquiryField,
  customerField,
  brands,
  errors = {},
  lineFooter,
  imageActions,
  feedback,
}: NewProductApplicationSheetProps) {
  const patch = (next: Partial<FormState>) => onChange({ ...value, ...next });
  const patchLine = (key: string, next: Partial<DraftLine>) =>
    patch({
      lines: value.lines.map((l) => (l.key === key ? { ...l, ...next } : l)),
    });

  const dash = (v: string | null | undefined) => (v && v.trim() ? v : '-');
  const text = (line: DraftLine, field: keyof DraftLine, label: string) =>
    readOnly ? (
      dash(line[field] as string)
    ) : (
      <Input
        aria-label={label}
        value={line[field] as string}
        onChange={(e) => patchLine(line.key, { [field]: e.target.value })}
      />
    );

  const editable = Boolean(feedback?.editable);
  const hasFeedback =
    Boolean(value.lead_time.trim()) ||
    value.lines.some((l) => l.cost_price.trim());
  const many = value.lines.length > 1;

  return (
    <div className="space-y-4">
      <div className="border">
        <div className="border-b bg-muted/40 px-3 py-3 text-center text-lg font-semibold tracking-tight">
          NEW PRODUCT APPLICATION
        </div>
        <Row label="REFF:">{applicationNo || '-'}</Row>
        <Row label="DATE:">
          {formatDateInMalaysia(createdAt ?? new Date()) || '-'}
        </Row>
        <Row label="SALES PERSON:">{salesPerson || '-'}</Row>
        {stockInquiryField !== undefined && (
          <Row label="STOCK INQUIRY:">{stockInquiryField}</Row>
        )}
      </div>

      {value.lines.map((line, index) => (
        <div key={line.key} data-testid="npa-product" className="border">
          <div className="flex items-center justify-between gap-2 border-b bg-muted/40 px-3 py-2">
            <span className="text-sm font-semibold">
              Product {index + 1} of {value.lines.length}
            </span>
            {!readOnly && many && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() =>
                  patch({
                    lines: value.lines.filter((l) => l.key !== line.key),
                  })
                }
              >
                Remove
              </Button>
            )}
          </div>
          <Row label="PRODUCT CODE:">
            {text(line, 'proposed_code', 'Product code')}
          </Row>
          <Row label="PRODUCT TYPE:" required>
            {text(line, 'description', 'Product type')}
          </Row>
          <Row label="DIMENSION:">{text(line, 'dimension', 'Dimension')}</Row>
          <Row label="MATERIAL:">{text(line, 'material', 'Material')}</Row>
          <Row label="THICKNESS:">{text(line, 'thickness', 'Thickness')}</Row>
          <Row label="PACKING">{text(line, 'packing', 'Packing')}</Row>
          <Row label="BRAND:">
            {readOnly ? (
              dash(line.brand_label)
            ) : (
              <SearchableSelect
                aria-label="Brand"
                value={line.brand_id}
                clearable
                truncateTriggerLabel
                wrapOptions
                placeholder="Search brand"
                fetchOptions={brands}
                selectedOption={
                  line.brand_id
                    ? { value: line.brand_id, label: line.brand_label }
                    : undefined
                }
                onChange={(v) => {
                  if (!v)
                    patchLine(line.key, { brand_id: '', brand_label: '' });
                }}
                onOptionChange={(opt) =>
                  opt &&
                  patchLine(line.key, {
                    brand_id: opt.value,
                    brand_label: opt.label,
                  })
                }
              />
            )}
          </Row>
          <Row label="IMAGE:">
            <ImageCell
              line={line}
              copyEnabled={
                line.id && imageActions
                  ? Boolean(imageActions.savedInquiryId) &&
                    imageActions.savedInquiryId === value.stock_inquiry_id
                  : Boolean(value.stock_inquiry_id)
              }
              inquiryId={
                line.id && imageActions
                  ? imageActions.savedInquiryId
                  : value.stock_inquiry_id
              }
              readOnly={readOnly}
              imageActions={imageActions}
              onStage={(files) => patchLine(line.key, { staged_images: files })}
              onStageCopy={(copies) =>
                patchLine(line.key, { staged_copies: copies })
              }
              onRemoveSaved={(image) =>
                patchLine(line.key, {
                  images: line.images.filter(
                    (i) => i.link_id !== image.link_id,
                  ),
                  removed_link_ids: [...line.removed_link_ids, image.link_id],
                })
              }
            />
          </Row>
          <Row label="QTY:">
            {readOnly ? (
              dash(line.expected_qty)
            ) : (
              <NumberInput
                inputMode="decimal"
                step="any"
                aria-label="Qty"
                value={line.expected_qty}
                error={errors[`expected_qty_${line.key}`]}
                onChange={(e) =>
                  patchLine(line.key, { expected_qty: e.target.value })
                }
              />
            )}
          </Row>
          {lineFooter && <Row label="OPENED AS">{lineFooter(line, index)}</Row>}
        </div>
      ))}
      {!readOnly && (
        <div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => patch({ lines: [...value.lines, blankLine()] })}
          >
            <Plus className="size-4" />
            Add product
          </Button>
          {errors.lines && (
            <p className="mt-2 text-xs text-destructive">{errors.lines}</p>
          )}
        </div>
      )}

      <div className="border">
        <Row label="CUSTOMER:">{customerField}</Row>
        <Row label="PROJECT:">
          {readOnly ? (
            dash(value.project_name)
          ) : (
            <Input
              aria-label="Project"
              value={value.project_name}
              onChange={(e) => patch({ project_name: e.target.value })}
            />
          )}
        </Row>
        <Row label="TARGET DELIVERY:">
          {readOnly ? (
            dash(value.needed_by && formatDateInMalaysia(value.needed_by))
          ) : (
            <Input
              aria-label="Target delivery"
              type="date"
              value={value.needed_by}
              onChange={(e) => patch({ needed_by: e.target.value })}
            />
          )}
        </Row>
        <Row label="REMARK:">
          {readOnly ? (
            <span className="whitespace-pre-wrap">{dash(value.remark)}</span>
          ) : (
            <Textarea
              aria-label="Remark"
              rows={3}
              value={value.remark}
              onChange={(e) => patch({ remark: e.target.value })}
            />
          )}
        </Row>
      </div>

      <div className="border">
        <div className="border-b bg-muted/40 px-3 py-2 text-center text-sm font-semibold">
          PURCHASING FEEDBACK
        </div>
        {!editable && !hasFeedback && (
          <p className="border-b px-3 py-2 text-sm text-muted-foreground">
            Purchasing fills this after approval.
          </p>
        )}
        {value.lines.map((line, index) => (
          <Row
            key={line.key}
            label="COST:"
            caption={many ? `Product ${index + 1}` : undefined}
          >
            {editable ? (
              <NumberInput
                inputMode="decimal"
                step="any"
                aria-label={`Cost for product ${index + 1}`}
                value={line.cost_price}
                onChange={(e) =>
                  patchLine(line.key, { cost_price: e.target.value })
                }
              />
            ) : (
              <span>
                {line.cost_price.trim() ? `MYR ${line.cost_price}` : '-'}
              </span>
            )}
          </Row>
        ))}
        <Row label="LEADTIME:">
          {editable ? (
            <Input
              aria-label="Lead time"
              value={value.lead_time}
              onChange={(e) => patch({ lead_time: e.target.value })}
            />
          ) : (
            value.lead_time.trim() || '-'
          )}
        </Row>
        {editable && (
          <div className="flex justify-end px-3 py-2">
            <Button
              type="button"
              size="sm"
              disabled={feedback?.saving}
              onClick={() => feedback?.onSave?.()}
            >
              Save feedback
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
