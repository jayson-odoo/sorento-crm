'use client';

import { useMemo, useState } from 'react';
import { ChevronsUpDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import type { ListQueryFieldMeta } from '@/lib/list-query/listQueryService';
import {
  groupOrderListFields,
  inferOrderFieldSubgroup,
  shortNestedOrderLineLabel,
} from '@/lib/list-query/orderFieldGroups';
import { cn } from '@/lib/utils';

type Props = {
  value: string;
  onFieldChange: (fieldKey: string) => void;
  filterable: ListQueryFieldMeta[];
};

/**
 * Hierarchical field picker for orders advanced filters (replaces flat Select).
 */
export function OrderFilterFieldSelect({ value, onFieldChange, filterable }: Props) {
  const [open, setOpen] = useState(false);
  const groups = useMemo(() => groupOrderListFields(filterable), [filterable]);
  const current = filterable.find((x) => x.field_key === value);
  const currentSub = current ? inferOrderFieldSubgroup(current) : null;
  const hasAnyLineFields =
    groups.lineDirect.length > 0 || groups.product.length > 0 || groups.warehouse.length > 0;
  const hasNestedLineGroups = groups.product.length > 0 || groups.warehouse.length > 0;

  function pickField(f: ListQueryFieldMeta) {
    onFieldChange(f.field_key);
    setOpen(false);
  }

  function LeafRow({ f, sub }: { f: ListQueryFieldMeta; sub?: 'product' | 'warehouse' }) {
    const text = sub ? shortNestedOrderLineLabel(f.label, sub) : f.label;
    const selected = value === f.field_key;
    return (
      <button
        type="button"
        className={cn(
          'flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-muted',
          selected && 'bg-accent font-medium',
        )}
        onClick={() => pickField(f)}
      >
        <span className="truncate">
          {text}
          {!sub && f.is_line_field ? null : ''}
        </span>
      </button>
    );
  }

  const defaultOpenOuter = ['fo', ...(hasAnyLineFields ? ['fl'] : [])];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="h-auto min-h-9 w-full justify-between gap-2 py-2 font-normal"
        >
          <span className="truncate text-left">
            {current ? (
              currentSub === 'product' ? (
                <>
                  <span className="text-muted-foreground">Product · </span>
                  {shortNestedOrderLineLabel(current.label, 'product')}
                </>
              ) : currentSub === 'warehouse' ? (
                <>
                  <span className="text-muted-foreground">Warehouse · </span>
                  {shortNestedOrderLineLabel(current.label, 'warehouse')}
                </>
              ) : (
                <>
                  {current.label}
                  {current.is_line_field && !currentSub ? null : ''}
                </>
              )
            ) : (
              <span className="text-muted-foreground">Choose field…</span>
            )}
          </span>
          <ChevronsUpDown className="size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(100vw-2rem,380px)] p-0" align="start">
        <div className="max-h-[min(360px,55vh)] overflow-y-auto p-2">
          <Accordion
            type="multiple"
            defaultValue={defaultOpenOuter}
            variant="outline"
            className="w-full space-y-2"
          >
            <AccordionItem value="fo" className="rounded-lg border border-border px-2">
              <AccordionTrigger className="py-2.5 text-sm font-semibold hover:no-underline">
                Order columns
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-0.5 border-s-2 border-primary/25 ps-2 pb-1">
                  {groups.order.map((f) => (
                    <LeafRow key={f.field_key} f={f} />
                  ))}
                </div>
              </AccordionContent>
            </AccordionItem>

            {hasAnyLineFields ? (
              <AccordionItem value="fl" className="rounded-lg border border-border px-2">
                <AccordionTrigger className="py-2.5 text-sm font-semibold hover:no-underline">
                  Line items
                </AccordionTrigger>
                <AccordionContent>
                  <div className="space-y-2 border-s-2 border-primary/25 ps-2 pb-1">
                    {groups.lineDirect.length > 0 ? (
                      <div className="space-y-0.5">
                        {groups.lineDirect.map((f) => (
                          <LeafRow key={f.field_key} f={f} />
                        ))}
                      </div>
                    ) : null}
                    {hasNestedLineGroups ? (
                      <div className="rounded-md bg-muted/40 p-2">
                        <p className="mb-1.5 px-1 text-xs text-muted-foreground">
                          Expand to choose product or warehouse fields
                        </p>
                        <Accordion
                          type="multiple"
                          defaultValue={[]}
                          variant="outline"
                          className="space-y-2 border-0 bg-transparent p-0 shadow-none"
                        >
                          {groups.product.length > 0 ? (
                            <AccordionItem
                              value="fp"
                              className="rounded-md border border-border/80 bg-background px-2"
                            >
                              <AccordionTrigger className="py-2 text-sm font-medium hover:no-underline">
                                Product
                              </AccordionTrigger>
                              <AccordionContent>
                                <div className="space-y-0.5">
                                  {groups.product.map((f) => (
                                    <LeafRow key={f.field_key} f={f} sub="product" />
                                  ))}
                                </div>
                              </AccordionContent>
                            </AccordionItem>
                          ) : null}
                          {groups.warehouse.length > 0 ? (
                            <AccordionItem
                              value="fw"
                              className="rounded-md border border-border/80 bg-background px-2"
                            >
                              <AccordionTrigger className="py-2 text-sm font-medium hover:no-underline">
                                Warehouse
                              </AccordionTrigger>
                              <AccordionContent>
                                <div className="space-y-0.5">
                                  {groups.warehouse.map((f) => (
                                    <LeafRow key={f.field_key} f={f} sub="warehouse" />
                                  ))}
                                </div>
                              </AccordionContent>
                            </AccordionItem>
                          ) : null}
                        </Accordion>
                      </div>
                    ) : null}
                  </div>
                </AccordionContent>
              </AccordionItem>
            ) : null}
          </Accordion>
        </div>
      </PopoverContent>
    </Popover>
  );
}
