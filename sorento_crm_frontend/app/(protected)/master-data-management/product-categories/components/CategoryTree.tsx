'use client';

import { useState } from 'react';
import { ChevronRight, ChevronDown, Folder, FolderOpen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { CategoryTreeItem } from '../types/category.types';

interface CategoryTreeProps {
  categories: CategoryTreeItem[];
  searchQuery?: string;
  level?: number;
}

export default function CategoryTree({ categories, searchQuery = '', level = 0 }: CategoryTreeProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggleExpand = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const filteredCategories = categories.filter((cat) =>
    cat.category_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    cat.category_code?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (filteredCategories.length === 0) {
    return <div className="text-sm text-muted-foreground py-4">No categories found</div>;
  }

  return (
    <div className="space-y-1">
      {filteredCategories.map((category) => {
        const hasChildren = category.children && category.children.length > 0;
        const isExpanded = expanded[category.id];

        return (
          <div key={category.id} style={{ paddingLeft: `${level * 24}px` }}>
            <div className="flex items-center gap-2 py-1.5 hover:bg-accent rounded-md px-2 group">
              {hasChildren ? (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 w-6 p-0"
                  onClick={() => toggleExpand(category.id)}
                >
                  {isExpanded ? (
                    <ChevronDown className="size-4" />
                  ) : (
                    <ChevronRight className="size-4" />
                  )}
                </Button>
              ) : (
                <div className="w-6" />
              )}
              {isExpanded || !hasChildren ? (
                <FolderOpen className="size-4 text-muted-foreground" />
              ) : (
                <Folder className="size-4 text-muted-foreground" />
              )}
              <span className="flex-1 font-medium text-sm">{category.category_name}</span>
              <span className="text-xs text-muted-foreground">{category.category_code}</span>
              {category.product_count !== undefined && (
                <Badge variant="secondary" size="sm">
                  {category.product_count}
                </Badge>
              )}
              <div className="opacity-0 group-hover:opacity-100 flex gap-1">
                <Button variant="ghost" size="sm" className="h-6">
                  Edit
                </Button>
                <Button variant="ghost" size="sm" className="h-6">
                  Delete
                </Button>
              </div>
            </div>
            {hasChildren && isExpanded && (
              <CategoryTree
                categories={category.children || []}
                searchQuery={searchQuery}
                level={level + 1}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
