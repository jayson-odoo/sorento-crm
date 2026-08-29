'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ChevronRight, ChevronDown, Folder, FolderOpen, ExternalLink, Edit, Copy, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { Badge, BadgeDot } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { CategoryTreeItem } from '../types/category.types';

interface CategoryTreeProps {
  categories: CategoryTreeItem[];
  searchQuery?: string;
  level?: number;
  onEdit?: (category: CategoryTreeItem) => void;
  onDuplicate?: (category: CategoryTreeItem) => void;
  onDelete?: (category: CategoryTreeItem) => void;
}

function flattenVisible(
  items: CategoryTreeItem[],
  level: number,
  expanded: Record<string, boolean>,
): { category: CategoryTreeItem; level: number }[] {
  const result: { category: CategoryTreeItem; level: number }[] = [];
  for (const cat of items) {
    result.push({ category: cat, level });
    if (cat.children?.length && expanded[cat.id]) {
      result.push(...flattenVisible(cat.children, level + 1, expanded));
    }
  }
  return result;
}

export default function CategoryTree({ categories, searchQuery = '', level = 0, onEdit, onDuplicate, onDelete }: CategoryTreeProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggleExpand = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const filteredCategories = useMemo(
    () =>
      categories.filter(
        (cat) =>
          cat.category_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          cat.category_code?.toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    [categories, searchQuery],
  );

  const visibleRows = useMemo(
    () => flattenVisible(filteredCategories, level, expanded),
    [filteredCategories, level, expanded],
  );

  if (filteredCategories.length === 0) {
    return <div className="text-sm text-muted-foreground py-4">No categories found</div>;
  }

  return (
    /* A fixed layout with percentage columns gave Name 24% of 375px - 90px, of
       which the indent and two icons took 60 - so a nested category read as
       three characters and an ellipsis. The columns size to their content now
       and the table scrolls sideways inside its own container, with Name pinned
       on the left exactly as the DataGrid pins its identifier. */
    <ScrollArea>
      <table className="w-auto min-w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-border bg-muted/50">
            <th className="sticky start-0 z-10 bg-muted/50 text-left font-medium text-muted-foreground px-3 py-2.5">
              Name
            </th>
            <th className="text-left font-medium text-muted-foreground px-3 py-2.5">Code</th>
            <th className="text-left font-medium text-muted-foreground px-3 py-2.5">Description</th>
            <th className="text-left font-medium text-muted-foreground px-3 py-2.5">Active</th>
            <th className="text-left font-medium text-muted-foreground px-3 py-2.5">Products</th>
            <th className="text-left font-medium text-muted-foreground px-3 py-2.5">Actions</th>
          </tr>
        </thead>
        <tbody>
          {visibleRows.map(({ category, level: rowLevel }) => {
            const hasChildren = category.children && category.children.length > 0;
            const isExpanded = expanded[category.id];

            return (
              <tr
                key={category.id}
                className="border-b border-border/70 hover:bg-accent/50 transition-colors group"
              >
                <td className="sticky start-0 z-10 bg-background px-3 py-2 align-middle group-hover:bg-accent/50">
                  <div
                    className="flex items-center gap-1.5"
                    style={{ paddingLeft: `${rowLevel * 20}px` }}
                  >
                    {hasChildren ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0 shrink-0"
                        onClick={() => toggleExpand(category.id)}
                      >
                        {isExpanded ? (
                          <ChevronDown className="size-4" />
                        ) : (
                          <ChevronRight className="size-4" />
                        )}
                      </Button>
                    ) : (
                      <span className="w-6 shrink-0" />
                    )}
                    {isExpanded || !hasChildren ? (
                      <FolderOpen className="size-4 text-muted-foreground shrink-0" />
                    ) : (
                      <Folder className="size-4 text-muted-foreground shrink-0" />
                    )}
                    <span className="font-medium whitespace-nowrap">{category.category_name}</span>
                  </div>
                </td>
                <td className="px-3 py-2 text-muted-foreground whitespace-nowrap">
                  {category.category_code}
                </td>
                <td
                  className="max-w-[28rem] truncate px-3 py-2 text-muted-foreground"
                  title={category.description ?? undefined}
                >
                  {category.description ?? '-'}
                </td>
                <td className="px-3 py-2">
                  <Badge
                    variant={category.is_active ? 'success' : 'secondary'}
                    size="sm"
                    className="shrink-0"
                  >
                    <BadgeDot />
                    {category.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </td>
                <td className="px-3 py-2">
                  {category.product_count !== undefined && (
                    <div className="flex items-center gap-1">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Badge variant="secondary" size="sm" className="cursor-help shrink-0 w-fit">
                            {category.product_count}
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent>Number of products in this category</TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="sm" className="h-6 px-1.5 shrink-0" asChild>
                            <Link
                              href={`/master-data-management/products?category=${category.id}`}
                              className="text-muted-foreground hover:text-foreground"
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <ExternalLink className="size-3.5" />
                              <span className="sr-only">View products (opens in new tab)</span>
                            </Link>
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>View products in this category</TooltipContent>
                      </Tooltip>
                    </div>
                  )}
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-1">
                    <Button
                      mode="icon"
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onEdit?.(category);
                      }}
                      title="Edit"
                    >
                      <Edit className="size-4" />
                    </Button>
                    <Button
                      mode="icon"
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDuplicate?.(category);
                      }}
                      title="Duplicate"
                    >
                      <Copy className="size-4" />
                    </Button>
                    <Button
                      mode="icon"
                      variant="ghost"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete?.(category);
                      }}
                      title="Delete"
                    >
                      <Trash2 className="size-4" />
                    </Button>
                    <ChevronRight className="text-muted-foreground/70 size-3.5 shrink-0" />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <ScrollBar orientation="horizontal" />
    </ScrollArea>
  );
}
