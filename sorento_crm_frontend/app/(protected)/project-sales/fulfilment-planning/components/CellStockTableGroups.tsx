'use client';

import * as React from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { GroupNode } from '@/components/common/group-by/groupByLevels';
import type { StockLine } from '../../_shared/lib/stockGroupLines';

/** The table's own cell classes, passed in so this file never imports CellStockTable back. */
export interface GroupCellClasses {
  chevron: string;
  body: string;
  foot: string;
  number: string;
}

interface GroupRowsProps {
  nodes: GroupNode<StockLine>[];
  /** Indent steps already taken by the row these hang under (a location or set row = 1). */
  baseDepth: number;
  columns: { key: string; signed?: boolean }[];
  classes: GroupCellClasses;
  locationColClassName: string;
  locationColStyle: React.CSSProperties | undefined;
  /** Level ids in play, so a line's muted second line leaves out what a level already says. */
  levels: readonly string[];
  isOpen: (key: string) => boolean;
  onToggle: (key: string) => void;
  /** Lines the dialog search lets through; group counts and sums never follow it. */
  showLine: (line: StockLine) => boolean;
}

const SUMMED = new Set(['on-hand', 'so', 'spo', 'po']);
const INDENT_PX = 16;

function isNegative(value: string): boolean {
  return Number(value) < 0;
}

export function GroupRows(props: GroupRowsProps) {
  const { nodes, baseDepth, columns, classes, locationColClassName, locationColStyle, isOpen, onToggle } = props;
  return (
    <>
      {nodes.map((node) => {
        const open = isOpen(node.key);
        return (
          <React.Fragment key={node.key}>
            <tr data-testid={`stock-group-${node.key}`}>
              <td className={cn(classes.chevron, classes.foot, 'px-1')}>
                <Button
                  type="button"
                  mode="icon"
                  variant="ghost"
                  size="sm"
                  className="size-5"
                  data-testid={`stock-group-toggle-${node.key}`}
                  aria-label={`${open ? 'Hide' : 'Show'} ${node.label}`}
                  aria-expanded={open}
                  onClick={() => onToggle(node.key)}
                >
                  {open ? (
                    <ChevronDown className="size-3.5" aria-hidden />
                  ) : (
                    <ChevronRight className="size-3.5" aria-hidden />
                  )}
                </Button>
              </td>
              <td className={cn(locationColClassName, classes.foot, 'max-w-0')} style={locationColStyle}>
                <div
                  className="flex min-w-0 items-baseline gap-2"
                  style={{ paddingInlineStart: (baseDepth + node.depth) * INDENT_PX }}
                >
                  <span className="truncate" title={node.label}>
                    {node.label}
                  </span>
                  <span className="shrink-0 font-normal text-muted-foreground">
                    {node.count === 1 ? '1 line' : `${node.count} lines`}
                  </span>
                </div>
              </td>
              {columns.map((column) => {
                const sum = SUMMED.has(column.key) ? node.sums[column.key] : undefined;
                return (
                  <td key={column.key} className={cn(classes.number, classes.foot)}>
                    {sum !== undefined ? (
                      <span
                        data-testid={`stock-group-${column.key}-${node.key}`}
                        className={cn('block truncate text-end tabular-nums', isNegative(sum) && 'text-destructive')}
                        title={sum}
                      >
                        {sum}
                      </span>
                    ) : null}
                  </td>
                );
              })}
            </tr>
            {open &&
              (node.children.length > 0 ? (
                <GroupRows {...props} nodes={node.children} />
              ) : (
                <LineRows {...props} lines={node.lines} depth={baseDepth + node.depth + 1} />
              ))}
          </React.Fragment>
        );
      })}
    </>
  );
}

const LINE_COLUMN = { 'On hand': 'on-hand', 'S/O': 'so', SPO: 'spo', PO: 'po' } as const;

/** What a line says beyond its group path: the values no level already names, then its date. */
function metaOf(line: StockLine, levels: readonly string[]): string {
  const skip = (id: string) => levels.includes(id);
  const parts = [
    line.type !== 'On hand' && !skip('location') ? line.location : null,
    skip('customer') ? null : line.customer,
    skip('supplier') ? null : line.supplier,
    skip('project') ? null : line.project,
    skip('agent') ? null : line.agent,
    line.date ? `${line.type === 'S/O' ? 'due' : 'expected'} ${formatDateInMalaysia(line.date)}` : null,
  ];
  return parts.filter(Boolean).join(' · ');
}

interface LineRowsProps extends Pick<GroupRowsProps, 'columns' | 'classes' | 'locationColClassName' | 'locationColStyle' | 'levels' | 'showLine'> {
  lines: StockLine[];
  depth: number;
}

export function LineRows({
  lines,
  depth,
  columns,
  classes,
  locationColClassName,
  locationColStyle,
  levels,
  showLine,
}: LineRowsProps) {
  return (
    <>
      {lines.filter(showLine).map((line) => {
        const meta = metaOf(line, levels);
        const ownColumn = LINE_COLUMN[line.type];
        const own = { 'on-hand': line.onHand, so: line.so, spo: line.spo, po: line.po }[ownColumn];
        return (
          <tr key={line.key} data-testid={`stock-line-${line.key}`}>
            <td className={cn(classes.chevron, classes.body)} />
            <td className={cn(locationColClassName, classes.body, 'max-w-0')} style={locationColStyle}>
              <div className="min-w-0" style={{ paddingInlineStart: depth * INDENT_PX }}>
                <div className="flex min-w-0 items-baseline gap-1.5">
                  <span className="shrink-0 text-muted-foreground">{line.type}</span>
                  {line.docNo && line.href ? (
                    <Link href={line.href} className="truncate font-medium text-primary hover:underline" title={line.docNo}>
                      {line.docNo}
                    </Link>
                  ) : (
                    <span className="truncate font-medium" title={line.location}>
                      {line.location}
                    </span>
                  )}
                </div>
                {meta ? (
                  <div
                    data-testid={`stock-line-meta-${line.key}`}
                    className="whitespace-normal break-words text-muted-foreground"
                  >
                    {meta}
                  </div>
                ) : null}
              </div>
            </td>
            {columns.map((column) => (
              <td key={column.key} className={cn(classes.number, classes.body)}>
                {column.key === ownColumn ? (
                  <span
                    data-testid={`stock-line-${column.key}-${line.key}`}
                    className={cn('block truncate text-end tabular-nums', isNegative(own) && 'text-destructive')}
                    title={own}
                  >
                    {own}
                  </span>
                ) : null}
              </td>
            ))}
          </tr>
        );
      })}
    </>
  );
}
