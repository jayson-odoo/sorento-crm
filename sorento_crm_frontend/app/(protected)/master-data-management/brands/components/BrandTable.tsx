'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { Edit, Copy, Trash2, ChevronRight, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { Brand } from '../types/brand.types';

interface BrandTableProps {
  brands: Brand[];
  searchQuery?: string;
  onEdit?: (brand: Brand) => void;
  onDuplicate?: (brand: Brand) => void;
  onDelete?: (brand: Brand) => void;
}

export default function BrandTable({
  brands,
  searchQuery = '',
  onEdit,
  onDuplicate,
  onDelete,
}: BrandTableProps) {
  const filteredBrands = useMemo(
    () =>
      brands.filter(
        (b) =>
          b.brand_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          b.brand_code?.toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    [brands, searchQuery],
  );

  if (filteredBrands.length === 0) {
    return (
      <div className="text-sm text-muted-foreground py-4">No brands found</div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full table-fixed border-collapse text-sm">
        <colgroup>
          <col style={{ width: '24%' }} />
          <col style={{ width: '12%' }} />
          <col style={{ width: '24%' }} />
          <col style={{ width: '10%' }} />
          <col style={{ width: '12%' }} />
          <col style={{ width: '18%' }} />
        </colgroup>
        <thead>
          <tr className="border-b border-border bg-muted/50">
            <th className="text-left font-medium text-muted-foreground px-3 py-2.5">
              Name
            </th>
            <th className="text-left font-medium text-muted-foreground px-3 py-2.5">
              Code
            </th>
            <th className="text-left font-medium text-muted-foreground px-3 py-2.5">
              Description
            </th>
            <th className="text-left font-medium text-muted-foreground px-3 py-2.5">
              Active
            </th>
            <th className="text-left font-medium text-muted-foreground px-3 py-2.5">
              Products
            </th>
            <th className="text-left font-medium text-muted-foreground px-3 py-2.5">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {filteredBrands.map((brand) => (
            <tr
              key={brand.id}
              className="border-b border-border/70 hover:bg-accent/50 transition-colors group"
            >
              <td className="px-3 py-2 align-middle">
                <span className="font-medium truncate block">
                  {brand.brand_name}
                </span>
              </td>
              <td className="px-3 py-2 text-muted-foreground truncate">
                {brand.brand_code}
              </td>
              <td
                className="px-3 py-2 text-muted-foreground truncate"
                title={brand.description ?? undefined}
              >
                {brand.description ?? '—'}
              </td>
              <td className="px-3 py-2">
                <Badge
                  variant={brand.is_active ? 'success' : 'secondary'}
                  size="sm"
                  appearance="ghost"
                  className="shrink-0"
                >
                  <BadgeDot />
                  {brand.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-1">
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Badge
                        variant="secondary"
                        size="sm"
                        className="cursor-help shrink-0 w-fit"
                      >
                        {brand.product_count ?? 0}
                      </Badge>
                    </TooltipTrigger>
                    <TooltipContent>
                      Number of products using this brand
                    </TooltipContent>
                  </Tooltip>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-1.5 shrink-0"
                        asChild
                      >
                        <Link
                          href={`/master-data-management/products?brand=${brand.id}`}
                          className="text-muted-foreground hover:text-foreground"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          <ExternalLink className="size-3.5" />
                          <span className="sr-only">
                            View products (opens in new tab)
                          </span>
                        </Link>
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent>View products with this brand</TooltipContent>
                  </Tooltip>
                </div>
              </td>
              <td className="px-3 py-2">
                <div className="flex items-center gap-1">
                  <Button
                    mode="icon"
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      onEdit?.(brand);
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
                      onDuplicate?.(brand);
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
                      onDelete?.(brand);
                    }}
                    title="Delete"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                  <ChevronRight className="text-muted-foreground/70 size-3.5 shrink-0" />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
