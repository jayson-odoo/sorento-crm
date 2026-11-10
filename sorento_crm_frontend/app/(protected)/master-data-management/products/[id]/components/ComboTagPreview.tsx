'use client';

/**
 * The combo as its default price tag template prints it, beside the description editor
 * (PRICETAG-COMBO-FORMAT). Drawn through `DesignViewer`, the renderer the request preview and the
 * PDF use, from the description as typed (before it is saved), so an edit is seen at once.
 */

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RichTextView } from '@/components/dealer-kit/RichTextView';
import { getProductTagData } from '@/app/(protected)/dealer-kit/services/tagDataService';
import { renderMergeFields } from '@/lib/dealer-kit/merge-fields';
import { richBlocksWithFields } from '@/lib/dealer-kit/product-block';
import type { TagBindingData, TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import DesignViewer from '@/components/dealer-kit/DesignViewer';
import { useComboTagTemplates } from '@/app/(protected)/dealer-kit/hooks/useProductTagTemplates';
import { useTagPreview } from '@/app/(protected)/dealer-kit/hooks/useTagPreview';
import { buildSingleTagSheet } from '@/lib/dealer-kit/request-tags';
import {
  designPayloadFromResponse,
  type TagSheetDesignPayload,
} from '@/lib/dealer-kit/design-payload';
import type {
  LinePartIn,
  TagPreviewLineInput,
} from '@/app/(auth)/portal/lib/price-tag-request-service';
import type { ProductTagTemplateItem } from '@/app/(protected)/dealer-kit/services/productTagTemplateService';
import type {
  ProductComboPartRow,
  ProductComboRow,
} from '../../types/productCombo.types';

const KEY = 'combo-preview';
/** The role a request line files an upgrade under (`tag_data_service._line_slots`). */
const UPGRADE = 'Upgrade';

/** What the reader can pick in the preview: each group of 2+ options, then the upgrades. */
export interface PreviewChoice {
  role: string;
  options: ProductComboPartRow[];
}

/** The pick-one groups (2+ options) in part order, then the upgrades as one choice. */
export function previewChoices(parts: ProductComboPartRow[]): PreviewChoice[] {
  const groups: PreviewChoice[] = [];
  for (const part of parts) {
    if (part.is_upgrade || !part.choice_group) continue;
    const group = groups.find((g) => g.role === part.choice_group);
    if (group) group.options.push(part);
    else groups.push({ role: part.choice_group, options: [part] });
  }
  const upgrades = parts.filter((part) => part.is_upgrade);
  return [
    ...groups.filter((g) => g.options.length > 1),
    ...(upgrades.length > 0 ? [{ role: UPGRADE, options: upgrades }] : []),
  ];
}

/**
 * The combo's parts as a request line sends them (COMBO-SETTINGS-UX rule 2): a fixed part placed, a
 * one-option group placed as its option, a picked option placed under its group, an unpicked group
 * open with its candidates, the upgrades last under `Upgrade`. A pick that is no longer an option of
 * its group counts as no pick.
 */
export function previewParts(
  parts: ProductComboPartRow[],
  picks: Record<string, string>,
): LinePartIn[] {
  const out: LinePartIn[] = [];
  const seen = new Set<string>();
  const optionsOf = (role: string) =>
    parts
      .filter((part) => !part.is_upgrade && part.choice_group === role)
      .map((part) => part.product_id);
  for (const part of parts) {
    if (part.is_upgrade) continue;
    if (!part.choice_group) {
      out.push({ product_id: part.product_id, role: null });
      continue;
    }
    const role = part.choice_group;
    if (seen.has(role)) continue;
    seen.add(role);
    const options = optionsOf(role);
    // A one-part group is a fixed part (owner round 1), placed with no role.
    if (options.length === 1) {
      out.push({ product_id: options[0], role: null });
      continue;
    }
    const picked = options.find((id) => id === picks[role]);
    out.push(
      picked ? { product_id: picked, role } : { role, candidates: options },
    );
  }
  const upgrades = parts
    .filter((part) => part.is_upgrade)
    .map((part) => part.product_id);
  if (upgrades.length > 0) {
    const picked = upgrades.find((id) => id === picks[UPGRADE]);
    out.push(
      picked
        ? { product_id: picked, role: UPGRADE }
        : { role: UPGRADE, candidates: upgrades },
    );
  }
  return out;
}

/**
 * The linked templates in the switcher's order (TAG-TEMPLATE-DUPLICATE item 4, owner 6 Nov):
 * the Default LP first, then the Default SP, then the rest as linked. The first is the one the
 * preview opens on.
 */
export function orderedLinks(
  rows: ProductTagTemplateItem[],
): ProductTagTemplateItem[] {
  const rank = (row: ProductTagTemplateItem) =>
    row.default_list ? 0 : row.default_selling ? 1 : row.is_default ? 2 : 3;
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => rank(a.row) - rank(b.row) || a.index - b.index)
    .map(({ row }) => row);
}

/** The price a link is previewed at: the LP default as list, the SP default as selling, else
 *  the template's own price type (unset or LP & SP read as list). */
function previewPriceType(link: ProductTagTemplateItem): 'list' | 'selling' {
  if (link.default_list) return 'list';
  if (link.default_selling) return 'selling';
  return link.price_type === 'selling' ? 'selling' : 'list';
}

/** "Default LP", "Default SP" or nothing: what the switcher says beside a template's name. */
function defaultTag(link: ProductTagTemplateItem): string | null {
  if (link.default_list && link.default_selling) return 'Default LP & SP';
  if (link.default_list) return 'Default LP';
  if (link.default_selling) return 'Default SP';
  return null;
}

/**
 * This combo's own tag data (its host with the combo, its parts, labels and part line), the same
 * the template designer previews a combo with. Works with no template at all, so the description can
 * always be shown with real values (owner round 1). Re-read when the combo or a part changes.
 */
export function useComboTagBinding(combo: ProductComboRow): TagBindingData | null {
  const query = useQuery({
    queryKey: [
      'combo-tag-data',
      combo.host_product_id,
      combo.id,
      combo.updated_at,
      combo.main_label ?? '',
      combo.parts.map((part) => `${part.id}:${part.label ?? ''}:${part.choice_group ?? ''}`).join('|'),
    ],
    queryFn: () => getProductTagData(combo.host_product_id, null, combo.id),
  });
  return useMemo(
    () => (query.data ? ({ kind: 'product', product: query.data } as TagBindingData) : null),
    [query.data],
  );
}

/** `binding` with the editor's drafts in place of the saved description and part line. */
export function withDrafts(
  binding: TagBindingData | null,
  description: string | null,
  partsLine: string | null | undefined,
): TagBindingData | null {
  if (!binding || binding.kind !== 'product' || !binding.product.combo) return binding;
  return {
    ...binding,
    product: {
      ...binding.product,
      combo: {
        ...binding.product.combo,
        description,
        ...(partsLine !== undefined ? { parts_line: partsLine } : {}),
      },
    },
  } as TagBindingData;
}

/** A layer stand-in, so a rich description splices `{{combo.parts}}` with its formatting. */
const DESCRIPTION_LAYER = { props: { kind: 'text', text: '' } } as unknown as Pick<TagLayer, 'props'>;

/** The description as the tag prints it, against this combo's real data. */
function DescriptionAsPrinted({ binding, description }: { binding: TagBindingData | null; description: string | null }) {
  if (!description || !binding) return null;
  const blocks = richBlocksWithFields(description, binding, 'print', DESCRIPTION_LAYER);
  return (
    <div className="space-y-1 rounded-md border bg-muted/30 p-3" data-testid="description-as-printed">
      <p className="text-xs text-muted-foreground">The description prints as:</p>
      {blocks ? (
        <RichTextView blocks={blocks} />
      ) : (
        <p className="whitespace-pre-line break-words text-sm">
          {renderMergeFields(description, binding, 'print')}
        </p>
      )}
    </div>
  );
}

/** Whether a template prints the combo description anywhere (a field or a bound slot). */
function printsDescription(layers: TagLayer[] | undefined): boolean {
  const reads = /\{\{\s*(combo\.description|combo\.parts|product\.price_tag_description)\s*\}\}/;
  return (layers ?? []).some((layer) => {
    if (layer.slot_binding === 'combo_description' || layer.slot_binding === 'price_tag_description') return true;
    const props = layer.props as { kind?: string; text?: string };
    return props?.kind === 'text' && reads.test(`${layer.text_override ?? ''} ${props.text ?? ''}`);
  });
}

export function ComboTagPreview({
  combo,
  description,
  partsLine,
  onBinding,
}: {
  combo: ProductComboRow;
  /** The description as it stands in the editor. */
  description: string | null;
  /** "Each part prints as" as it stands in its editor; absent = the saved one. */
  partsLine?: string | null;
  /** Hands this combo's real tag data up (the description's Insert field previews against it). */
  onBinding?: (binding: TagBindingData | null) => void;
}) {
  const links = useComboTagTemplates(combo.id);
  const ordered = useMemo(() => orderedLinks(links.data ?? []), [links.data]);
  // The reader's pick among the linked templates; falls back to the first (Default LP) when
  // nothing is picked yet or the picked one was unlinked.
  const [pickedId, setPickedId] = useState<string | null>(null);
  useEffect(() => {
    if (pickedId && !ordered.some((row) => row.id === pickedId))
      setPickedId(null);
  }, [ordered, pickedId]);
  const link = ordered.find((row) => row.id === pickedId) ?? ordered[0] ?? null;
  // The reader's preview picks, by group: never saved, and a pick that is no longer an option reads
  // as no pick (`previewParts`), so a removed part needs no clean-up here.
  const [picks, setPicks] = useState<Record<string, string>>({});
  const choices = useMemo(() => previewChoices(combo.parts), [combo.parts]);
  const parts = useMemo(
    () => previewParts(combo.parts, picks),
    [combo.parts, picks],
  );
  const line: TagPreviewLineInput = {
    key: KEY,
    line_type: 'product',
    product_id: combo.host_product_id,
    product_set_id: null,
    combo_id: combo.id,
    parts,
    promotion_id: null,
    manual_sell_price: null,
    tag_template_id: link?.id ?? null,
    price_type: link ? previewPriceType(link) : 'list',
  };
  // The server draws the line (slots, parts, photos, prices) exactly as the request preview and
  // the PDF do; only a published default can be drawn.
  const preview = useTagPreview(line, !!link && link.published);
  const real = useComboTagBinding(combo);
  useEffect(() => {
    onBinding?.(real);
  }, [real, onBinding]);
  const binding = withDrafts(real, description, partsLine);
  const asPrinted = <DescriptionAsPrinted binding={binding} description={description} />;

  const payload = useMemo<TagSheetDesignPayload | null>(() => {
    const row = preview.data?.lines[0];
    const template = preview.data?.templates[KEY];
    if (!preview.data || !row || !template) return null;
    const tagId = row.tag_id ?? row.line_id ?? KEY;
    const doc = buildSingleTagSheet(
      {
        id: tagId,
        quantity: 1,
        line: {
          id: row.line_id ?? KEY,
          line_type: 'product',
          product_id: combo.host_product_id,
          product_set_id: null,
          quantity: 1,
        },
      },
      template,
      () => 'combo-preview-tag',
    );
    // Only the description is the editor's unsaved draft; everything else is the server's.
    const drawn = {
      ...row,
      combo: {
        id: combo.id,
        name: combo.name,
        free_items: null,
        accessories: [],
        choices: [],
        upgrades: [],
        ...(row.combo ?? {}),
        description,
        ...(partsLine !== undefined ? { parts_line: partsLine } : {}),
      },
    };
    return designPayloadFromResponse({
      doc,
      lines: [drawn],
      assets: preview.data.assets,
      images: preview.data.images,
      fonts: preview.data.fonts,
    });
  }, [preview.data, combo, description, partsLine]);

  // The switcher (item 4), shown only when there is a choice to make. "Open" in the viewer opens
  // whatever is drawn, so it opens the selected template.
  const switcher =
    ordered.length > 1 ? (
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        aria-label="Template to preview"
        value={link?.id ?? ''}
        onValueChange={(value) => {
          if (value) setPickedId(value);
        }}
        className="flex-wrap"
      >
        {ordered.map((row) => {
          const tag = defaultTag(row);
          return (
            <ToggleGroupItem
              key={row.id}
              value={row.id}
              aria-label={tag ? `${row.name} (${tag})` : row.name}
              title={tag ? `${row.name} (${tag})` : row.name}
              className="max-w-48 px-2 text-xs"
            >
              <span className="truncate">{row.name}</span>
            </ToggleGroupItem>
          );
        })}
      </ToggleGroup>
    ) : null;

  // One picker per pick-one group and one for the upgrades (Q1 (a): starts on No pick).
  const pickers =
    // Only when there is a tag to redraw: a pick against "No price tag template" changes nothing.
    choices.length > 0 && link?.published ? (
      <div className="flex flex-wrap gap-2">
        {choices.map((choice) => {
          const value = choice.options.some(
            (o) => o.product_id === picks[choice.role],
          )
            ? picks[choice.role]
            : '';
          return (
            <div key={choice.role} className="w-full min-w-0 space-y-1 sm:w-52">
              <p className="text-xs text-muted-foreground">{choice.role}</p>
              <SearchableSelect
                clearable
                truncateTriggerLabel
                aria-label={`Preview ${choice.role}`}
                value={value}
                onChange={(next) =>
                  setPicks((current) => ({
                    ...current,
                    [choice.role]: next || '',
                  }))
                }
                options={choice.options.map((option) => ({
                  value: option.product_id,
                  label: option.code,
                }))}
                placeholder={choice.role === UPGRADE ? 'No upgrade' : 'No pick'}
              />
            </div>
          );
        })}
      </div>
    ) : null;

  return (
    <div className="space-y-2">
      {pickers}
      {drawn()}
    </div>
  );

  function drawn() {
    if (links.isLoading || (link?.published && preview.isLoading))
      return <SectionSkeleton rows={4} />;
    if (links.isError || preview.isError) {
      return (
        <div className="rounded-lg border border-dashed p-4 text-center">
          <p className="text-sm text-muted-foreground">
            Could not load the tag preview
          </p>
        </div>
      );
    }
    if (!payload) {
      return (
        <div className="space-y-2">
          {switcher}
          <div className="rounded-lg border border-dashed p-4 text-center">
            <p className="text-sm text-muted-foreground">
              {link
                ? 'No published price tag template'
                : 'No price tag template linked'}
            </p>
          </div>
          {asPrinted}
        </div>
      );
    }
    const template = preview.data?.templates[KEY] as { doc?: { layers?: TagLayer[] } } | undefined;
    const missing = !printsDescription(template?.doc?.layers);
    return (
      <div className="space-y-2">
        <DesignViewer
          title="Tag preview"
          docNumber={link ? `${combo.name} - ${link.name}` : combo.name}
          payload={payload}
          headerActions={switcher}
        />
        {missing ? (
          <>
            <p className="text-sm text-muted-foreground">
              &quot;{link?.name}&quot; has no field that prints the combo description.
            </p>
            {asPrinted}
          </>
        ) : null}
      </div>
    );
  }
}

export default ComboTagPreview;
