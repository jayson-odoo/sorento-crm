'use client';

import { useState } from 'react';
import { MousePointerSquareDashed, Package } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Textarea } from '@/components/ui/textarea';
import type { Block, BlockProps } from '@/lib/dealer-kit/types';
import { MOCK_COLLECTIONS, MOCK_TILE_TEMPLATES, MOCK_BUNDLES } from '../__mocks__/catalogue';
import {
  EMPTY_SELECTION,
  ProductPickerDialog,
  type ProductSelection,
} from './ProductPickerDialog';

/**
 * Editing the selected block's properties.
 *
 * Until now the canvas could place blocks but nothing could change what was IN
 * them, so a heading was stuck on its placeholder text. This is where that is
 * fixed and where product binding lives.
 *
 * A collection block stores a `collectionId`, a `tileTemplateId` and per
 * breakpoint column counts - and nothing else. No product list, no prices. What
 * a reader eventually sees is resolved server-side per viewer, so the same saved
 * document serves staff, a dealer and a consumer (AC-G1).
 */

const TEXT_SCALES = [
  { value: 'sm', label: 'Small' },
  { value: 'base', label: 'Body' },
  { value: 'lg', label: 'Large' },
  { value: 'xl', label: 'Extra large' },
  { value: '2xl', label: 'Display' },
];

const ALIGNMENTS = [
  { value: 'left', label: 'Left' },
  { value: 'center', label: 'Centre' },
  { value: 'right', label: 'Right' },
];

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-xs" htmlFor={htmlFor}>
        {label}
      </Label>
      {children}
    </div>
  );
}

export function BlockInspector({
  block,
  selection,
  onChangeProps,
  onChangeSelection,
}: {
  block: Block | null;
  /** The page-scoped product selection behind a collection block, if any. */
  selection: ProductSelection;
  onChangeProps: (next: BlockProps) => void;
  onChangeSelection: (next: ProductSelection) => void;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);

  if (!block) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Block</CardTitle>
        </CardHeader>
        <CardContent className="pb-4">
          <div className="rounded-lg border border-dashed border-border p-4 text-center">
            <MousePointerSquareDashed
              className="mx-auto size-4 text-muted-foreground"
              aria-hidden
            />
            <p className="mt-2 text-xs font-medium text-foreground">Nothing selected</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Click a block on the canvas to edit it.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const props = block.props;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between gap-2 text-sm">
          <span className="capitalize">{block.type}</span>
          <Badge variant="outline" appearance="ghost" className="text-[10px]">
            block
          </Badge>
        </CardTitle>
      </CardHeader>

      <CardContent className="flex flex-col gap-3 pb-4">
        {(props.kind === 'text' || props.kind === 'heading') && (
          <>
            <Field label="Text">
              <Textarea
                rows={3}
                value={props.text}
                aria-label="Block text"
                onChange={(event) => onChangeProps({ ...props, text: event.target.value })}
              />
            </Field>

            <Field label="Size" htmlFor="dk-text-size">
              <SearchableSelect
                id="dk-text-size"
                value={props.scale ?? 'base'}
                onChange={(value) =>
                  onChangeProps({ ...props, scale: value as typeof props.scale })
                }
                options={TEXT_SCALES}
              />
            </Field>

            <Field label="Alignment" htmlFor="dk-text-align">
              <SearchableSelect
                id="dk-text-align"
                value={props.align ?? 'left'}
                onChange={(value) =>
                  onChangeProps({ ...props, align: value as typeof props.align })
                }
                options={ALIGNMENTS}
              />
            </Field>
          </>
        )}

        {(props.kind === 'image' || props.kind === 'asset') && (
          <Field label="Alt text">
            <Input
              value={props.alt ?? ''}
              aria-label="Alt text"
              placeholder="Describe the image"
              onChange={(event) => onChangeProps({ ...props, alt: event.target.value })}
            />
          </Field>
        )}

        {props.kind === 'collection' && (
          <>
            <Button
              variant="outline"
              size="sm"
              className="justify-start"
              onClick={() => setPickerOpen(true)}
            >
              <Package className="size-4" />
              Choose products
            </Button>

            <p className="text-xs text-muted-foreground">
              {selection.pinnedProductIds.length === 0 && !selection.conditions
                ? 'Nothing chosen yet. The block stays empty until it has products.'
                : 'Products are resolved when the page is viewed, so prices follow the reader.'}
            </p>

            <Field label="Reusable collection" htmlFor="dk-collection">
              <SearchableSelect
                id="dk-collection"
                clearable
                value={props.collectionId ?? ''}
                onChange={(value) => onChangeProps({ ...props, collectionId: value || null })}
                options={MOCK_COLLECTIONS.map((collection) => ({
                  value: collection.id,
                  label: `${collection.name} (${collection.memberCount})`,
                }))}
                placeholder="Use this page's own selection"
              />
            </Field>

            <Field label="Tile design" htmlFor="dk-tile-template">
              <SearchableSelect
                id="dk-tile-template"
                clearable
                value={props.tileTemplateId ?? ''}
                onChange={(value) => onChangeProps({ ...props, tileTemplateId: value || null })}
                options={MOCK_TILE_TEMPLATES.map((template) => ({
                  value: template.id,
                  label: template.name,
                }))}
                placeholder="Pick a tile design"
              />
            </Field>

            <div className="grid grid-cols-3 gap-2">
              {(['desktop', 'tablet', 'mobile'] as const).map((breakpoint) => (
                <Field key={breakpoint} label={`${breakpoint} cols`}>
                  <Input
                    type="number"
                    min={1}
                    max={8}
                    value={props.columns[breakpoint]}
                    aria-label={`Tiles across on ${breakpoint}`}
                    onChange={(event) =>
                      onChangeProps({
                        ...props,
                        columns: {
                          ...props.columns,
                          [breakpoint]: Math.max(1, Number(event.target.value) || 1),
                        },
                      })
                    }
                  />
                </Field>
              ))}
            </div>

            <p className="text-xs text-muted-foreground">
              Tiles across is the block&apos;s own setting, which is why stacking the block
              full-width on a phone does not make a four-across product grid.
            </p>
          </>
        )}

        {props.kind === 'bundle' && (
          <>
            <Field label="Bundle" htmlFor="dk-bundle">
              <SearchableSelect
                id="dk-bundle"
                clearable
                value={props.bundleId ?? ''}
                onChange={(value) => onChangeProps({ ...props, bundleId: value || null })}
                options={MOCK_BUNDLES.map((bundle) => ({
                  value: bundle.id,
                  label: `${bundle.name} · ${bundle.price}`,
                }))}
                placeholder="Pick a bundle"
              />
            </Field>
            <p className="text-xs text-muted-foreground">
              A bundle shows as one price with its parts beneath. Whether it can be ordered is
              worked out from its parts each time it is viewed, so a discontinued part takes it
              out of stock automatically.
            </p>
          </>
        )}

        {props.kind === 'spacer' && (
          <p className="text-xs text-muted-foreground">
            A spacer has nothing to configure. Resize it on the canvas.
          </p>
        )}
      </CardContent>

      <ProductPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        value={selection ?? EMPTY_SELECTION}
        onSave={onChangeSelection}
      />
    </Card>
  );
}
