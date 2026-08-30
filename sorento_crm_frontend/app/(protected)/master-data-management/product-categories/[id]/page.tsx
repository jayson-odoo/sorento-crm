'use client';

import { use, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Check, ExternalLink, Loader2, Pencil, Trash2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList, { useBackToListHref } from '@/components/common/BackToList';
import DetailActions from '@/components/common/DetailActions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import type { RecordAction } from '@/components/common/recordActions';
import {
  useCategoriesTree,
  useCategory,
  useUpdateCategory,
} from '../hooks/useProductCategories';
import type { CategoryTreeItem } from '../types/category.types';
import { formatDate } from '@/lib/helpers';

const LIST_PATH = '/master-data-management/product-categories';

/**
 * The product category record: one page that reads and edits, in the same
 * layout.
 *
 * The tree's row used to end in a chevron that led nowhere, and editing meant a
 * lightbox opened from an icon button. The row opens this page now, and Edit
 * swaps each value for its input where it stands (ADR product standards).
 *
 * Children come from the tree query rather than a second endpoint: the list
 * already holds the whole tree, so asking again would be a second answer to the
 * same question.
 */
interface Draft {
  category_code: string;
  category_name: string;
  description: string;
  is_active: boolean;
  display_order: string;
}

const Empty = ({ children = 'Not set' }: { children?: string }) => (
  <span className="text-muted-foreground">{children}</span>
);

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
    <div className="grid gap-1.5">
      <Label htmlFor={htmlFor} className="text-sm text-muted-foreground font-normal">
        {label}
      </Label>
      <div className="text-sm font-medium">{children}</div>
    </div>
  );
}

/** Flattens the tree so a category can be found by id without a second fetch. */
function flatten(items: CategoryTreeItem[]): CategoryTreeItem[] {
  return items.flatMap((item) => [item, ...flatten(item.children ?? [])]);
}

export default function ProductCategoryDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const backHref = useBackToListHref(LIST_PATH);
  const { data: category, isLoading } = useCategory(id);
  const { data: tree = [] } = useCategoriesTree();
  const update = useUpdateCategory();

  // Delete asks nothing (D7): the countdown replaces the primary button and the
  // server applies it when the window lapses. A category still carrying products
  // is refused there, and the refusal arrives as the countdown's error.
  const deletion = useDeferredAction({
    actionKey: 'product_category.delete',
    entityType: 'product_category',
    entityId: id,
    verb: 'Deleting',
    subject: category ? `${category.category_name} (${category.category_code})` : '',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Category deleted',
    invalidateKeys: [['product-categories-tree'], ['product-category-select']],
    onCommitted: () => router.push(backHref),
  });

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);

  const header = (
    <PageHeader
      title="Product Category"
      actions={<BackToList listPath={LIST_PATH} label="Back to product categories" />}
    />
  );

  if (isLoading) {
    return (
      <>
        <Container>{header}</Container>
        <Container>
          <div className="space-y-6">
            <Skeleton className="h-10 w-64" />
            <Skeleton className="h-96 w-full" />
          </div>
        </Container>
      </>
    );
  }

  if (!category) {
    return (
      <>
        <Container>{header}</Container>
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Product category not found</p>
            <div className="mt-4 flex justify-center">
              <BackToList listPath={LIST_PATH} label="Back to product categories" />
            </div>
          </div>
        </Container>
      </>
    );
  }

  const flat = flatten(tree);
  const parent = category.parent_category_id
    ? flat.find((item) => item.id === category.parent_category_id)
    : undefined;
  const inTree = flat.find((item) => item.id === id);
  const children = inTree?.children ?? [];
  // The single-category endpoint does not carry a product count; the tree the
  // list already holds does, so the number comes from whichever has it.
  const productCount = category.product_count ?? inTree?.product_count ?? null;

  const startEdit = () => {
    setDraft({
      category_code: category.category_code,
      category_name: category.category_name,
      description: category.description ?? '',
      is_active: category.is_active,
      display_order: String(category.display_order ?? 0),
    });
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraft(null);
  };

  const handleSave = async () => {
    if (!draft) return;
    await update.mutateAsync({
      id,
      data: {
        category_code: draft.category_code.trim(),
        category_name: draft.category_name.trim(),
        description: draft.description.trim() || undefined,
        is_active: draft.is_active,
        display_order: Number(draft.display_order) || 0,
      },
    });
    cancelEdit();
  };

  const canSave =
    !!draft &&
    draft.category_code.trim().length > 0 &&
    draft.category_name.trim().length > 0 &&
    !update.isPending;

  const actions: RecordAction[] = [
    {
      key: 'product_category.delete',
      label: 'Delete category',
      icon: Trash2,
      kind: 'destructive',
      disabled: deletion.isPending,
      run: deletion.start,
    },
  ];

  return (
    <>
      <Container>{header}</Container>

      <Container>
        <div className="space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="space-y-1 min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-2xl font-bold break-words min-w-0">
                  {category.category_name}
                </h2>
                <Badge variant={category.is_active ? 'success' : 'secondary'}>
                  {category.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                Category code: {category.category_code}
              </p>
            </div>

            {editing ? (
              <div className="flex flex-wrap items-center justify-end gap-2">
                <Button variant="outline" onClick={cancelEdit} disabled={update.isPending}>
                  <X className="size-4" /> Cancel
                </Button>
                <Button onClick={() => void handleSave()} disabled={!canSave}>
                  {update.isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <Check className="size-4" />
                  )}
                  Save category
                </Button>
              </div>
            ) : (
              <DetailActions
                actions={actions}
                gearLabel="Category options"
                pendingAction={deletion.countdown}
                primary={
                  <Button onClick={startEdit}>
                    <Pencil className="size-4" /> Edit
                  </Button>
                }
              />
            )}
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Basic information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Field label="Category code" htmlFor="category-code">
                  {editing && draft ? (
                    <Input
                      id="category-code"
                      value={draft.category_code}
                      onChange={(e) => setDraft({ ...draft, category_code: e.target.value })}
                    />
                  ) : (
                    category.category_code
                  )}
                </Field>

                <Field label="Category name" htmlFor="category-name">
                  {editing && draft ? (
                    <Input
                      id="category-name"
                      value={draft.category_name}
                      onChange={(e) => setDraft({ ...draft, category_name: e.target.value })}
                    />
                  ) : (
                    category.category_name
                  )}
                </Field>

                <Field label="Description" htmlFor="category-description">
                  {editing && draft ? (
                    <Textarea
                      id="category-description"
                      rows={3}
                      value={draft.description}
                      onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                    />
                  ) : category.description ? (
                    <span className="whitespace-pre-wrap font-normal">
                      {category.description}
                    </span>
                  ) : (
                    <Empty>No description yet</Empty>
                  )}
                </Field>

                <Field label="Display order" htmlFor="category-order">
                  {editing && draft ? (
                    <Input
                      id="category-order"
                      type="number"
                      min={0}
                      value={draft.display_order}
                      onChange={(e) => setDraft({ ...draft, display_order: e.target.value })}
                    />
                  ) : (
                    (category.display_order ?? 0)
                  )}
                </Field>

                <Field label="Status" htmlFor="category-active">
                  {editing && draft ? (
                    <div className="flex items-center gap-2">
                      <Switch
                        id="category-active"
                        checked={draft.is_active}
                        onCheckedChange={(value) => setDraft({ ...draft, is_active: value })}
                      />
                      <span>{draft.is_active ? 'Active' : 'Inactive'}</span>
                    </div>
                  ) : (
                    <Badge variant={category.is_active ? 'success' : 'secondary'}>
                      {category.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  )}
                </Field>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Placement</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* The parent is set by dragging in the tree, so it is read-only
                    here in both modes rather than offering an input that would
                    disagree with the list. */}
                <Field label="Parent category">
                  {parent ? (
                    <Link href={`${LIST_PATH}/${parent.id}`} className="text-primary hover:underline">
                      {parent.category_name}
                    </Link>
                  ) : (
                    <Empty>A top-level category</Empty>
                  )}
                </Field>

                <Field label="Sub-categories">
                  {children.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {children.map((child) => (
                        <Button key={child.id} variant="outline" size="sm" asChild>
                          <Link href={`${LIST_PATH}/${child.id}`}>{child.category_name}</Link>
                        </Button>
                      ))}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <Empty>No sub-categories</Empty>
                      <div>
                        <Button variant="outline" size="sm" asChild>
                          <Link href={LIST_PATH}>Add one from the tree</Link>
                        </Button>
                      </div>
                    </div>
                  )}
                </Field>

                <Field label="Products in this category">
                  {productCount != null ? (
                    <div className="space-y-2">
                      <div>{productCount}</div>
                      <div>
                        <Button variant="outline" size="sm" asChild>
                          <Link
                            href={`/master-data-management/products?category_id=${category.id}`}
                          >
                            <ExternalLink className="size-3.5" /> View products
                          </Link>
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <Empty>Not counted</Empty>
                  )}
                </Field>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Record</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Field label="Created">{formatDate(new Date(category.created_at))}</Field>
                <Field label="Last updated">
                  {category.updated_at ? formatDate(new Date(category.updated_at)) : <Empty />}
                </Field>
              </CardContent>
            </Card>
          </div>
        </div>
      </Container>
    </>
  );
}
