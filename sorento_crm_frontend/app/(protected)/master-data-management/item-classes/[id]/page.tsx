'use client';

import { use, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Check, Loader2, Pencil, Trash2, X } from 'lucide-react';
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
import type { RecordAction } from '@/components/common/recordActions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { formatDate } from '@/lib/helpers';
import {
  itemClassesPagerQuery,
  useItemClass,
  useUpdateItemClass,
} from '../hooks/useItemClasses';

const LIST_PATH = '/master-data-management/item-classes';

interface Draft {
  item_class_code: string;
  item_class_name: string;
  description: string;
  is_active: boolean;
}

const Empty = ({ children = 'Not set' }: { children?: string }) => (
  <span className="text-muted-foreground">{children}</span>
);

/** A label above its value, or above its input while editing. */
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

/** The item class record: view and edit are the same layout; Edit swaps values for inputs. */
export default function ItemClassDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const backHref = useBackToListHref(LIST_PATH);
  const { data: itemClass, isLoading } = useItemClass(id);
  const update = useUpdateItemClass();

  const deletion = useDeferredAction({
    actionKey: 'item_class.delete',
    entityType: 'item_class',
    entityId: id,
    verb: 'Deleting',
    subject: itemClass ? `${itemClass.item_class_name} (${itemClass.item_class_code})` : '',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Item class deleted',
    invalidateKeys: [['item-classes'], ['item-class-select']],
    onCommitted: () => router.push(backHref),
  });

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);

  const header = (
    <PageHeader
      title="Item Class"
      actions={<BackToList listPath={LIST_PATH} label="Back to item classes" />}
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

  if (!itemClass) {
    return (
      <>
        <Container>{header}</Container>
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Item class not found</p>
            <div className="mt-4 flex justify-center">
              <BackToList listPath={LIST_PATH} label="Back to item classes" />
            </div>
          </div>
        </Container>
      </>
    );
  }

  const startEdit = () => {
    setDraft({
      item_class_code: itemClass.item_class_code,
      item_class_name: itemClass.item_class_name,
      description: itemClass.description ?? '',
      is_active: itemClass.is_active,
    });
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraft(null);
  };

  const handleSave = async () => {
    if (!draft) return;
    try {
      await update.mutateAsync({
        id,
        data: {
          item_class_code: draft.item_class_code.trim(),
          item_class_name: draft.item_class_name.trim(),
          description: draft.description.trim() || null,
          is_active: draft.is_active,
        },
      });
      cancelEdit();
    } catch {
      // The mutation hook surfaces the extracted error as a toast.
    }
  };

  const canSave =
    !!draft &&
    draft.item_class_code.trim().length > 0 &&
    draft.item_class_name.trim().length > 0 &&
    !update.isPending;

  const actions: RecordAction[] = [
    {
      key: 'item_class.delete',
      label: 'Delete item class',
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
                  {itemClass.item_class_name}
                </h2>
                <Badge variant={itemClass.is_active ? 'success' : 'secondary'}>
                  {itemClass.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                Item class code: {itemClass.item_class_code}
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
                  Save item class
                </Button>
              </div>
            ) : (
              <DetailActions
                actions={actions}
                gearLabel="Item class options"
                pendingAction={deletion.countdown}
                pager={{
                  ...itemClassesPagerQuery,
                  detailPath: LIST_PATH,
                  currentId: id,
                  ariaLabel: 'item class',
                }}
                primary={
                  <Button onClick={startEdit}>
                    <Pencil className="size-4" /> Edit
                  </Button>
                }
              />
            )}
          </div>

          {/* Read-only metadata sits directly under the header, never in a tab body. */}
          <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
            <div>
              <span className="text-muted-foreground">Created </span>
              {formatDate(new Date(itemClass.created_at))}
            </div>
            <div>
              <span className="text-muted-foreground">Last updated </span>
              {itemClass.updated_at ? formatDate(new Date(itemClass.updated_at)) : <Empty />}
            </div>
            <div>
              <span className="text-muted-foreground">Products </span>
              {itemClass.product_count}
            </div>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Basic information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Code" htmlFor="item-class-code">
                {editing && draft ? (
                  <Input
                    id="item-class-code"
                    maxLength={50}
                    value={draft.item_class_code}
                    onChange={(e) => setDraft({ ...draft, item_class_code: e.target.value })}
                  />
                ) : (
                  itemClass.item_class_code
                )}
              </Field>

              <Field label="Name" htmlFor="item-class-name">
                {editing && draft ? (
                  <Input
                    id="item-class-name"
                    maxLength={100}
                    value={draft.item_class_name}
                    onChange={(e) => setDraft({ ...draft, item_class_name: e.target.value })}
                  />
                ) : (
                  itemClass.item_class_name
                )}
              </Field>

              <Field label="Description" htmlFor="item-class-description">
                {editing && draft ? (
                  <Textarea
                    id="item-class-description"
                    rows={3}
                    value={draft.description}
                    onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  />
                ) : itemClass.description ? (
                  <span className="whitespace-pre-wrap font-normal">{itemClass.description}</span>
                ) : (
                  <Empty>No description yet</Empty>
                )}
              </Field>

              <Field label="Status" htmlFor="item-class-active">
                {editing && draft ? (
                  <div className="flex items-center gap-2">
                    <Switch
                      id="item-class-active"
                      checked={draft.is_active}
                      onCheckedChange={(value) => setDraft({ ...draft, is_active: value })}
                    />
                    <span>{draft.is_active ? 'Active' : 'Inactive'}</span>
                  </div>
                ) : (
                  <Badge variant={itemClass.is_active ? 'success' : 'secondary'}>
                    {itemClass.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                )}
              </Field>
            </CardContent>
          </Card>
        </div>
      </Container>
    </>
  );
}
