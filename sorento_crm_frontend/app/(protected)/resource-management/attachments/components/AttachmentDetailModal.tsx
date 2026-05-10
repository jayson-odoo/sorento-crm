'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { ChevronDown, Download, ExternalLink, Eye, Link2, LoaderCircleIcon, Plus, RefreshCw, SlidersHorizontal, Trash2, Unlink } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Command,
  CommandCheck,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { formatDate } from '@/lib/helpers';
import {
  useDeleteAttachment,
  useDownloadAttachment,
  useResubmitAttachmentWebhook,
  useRestoreAttachment,
  useUpdateAttachment,
} from '../hooks/useAttachments';
import { getAttachmentMetadata } from '../services/attachmentService';
import type { Attachment } from '../types/attachment.types';
import type { LinkedEntityRef } from '../types/attachment.types';
import RecordNavigation from '@/components/common/RecordNavigation';
import AttachmentDeleteDialog from './attachment-delete-dialog';
import ManageFieldLinksDialog from './ManageFieldLinksDialog';
import EditAttachmentTypeDialog from './EditAttachmentTypeDialog';
import { useCreateProductAttachment, useDeleteProductAttachment } from '@/app/(protected)/master-data-management/product-attachments/hooks/useProductAttachments';
import { useCreatePromotionAttachment, useDeletePromotionAttachment } from '@/app/(protected)/marketing-management/promotion-attachments/hooks/usePromotionAttachments';
import { useForms } from '@/app/(protected)/forms-management/forms/hooks/useForms';
import { useUpdateForm } from '@/app/(protected)/forms-management/forms/hooks/useForms';
import { getProducts } from '@/app/(protected)/master-data-management/products/services/productService';
import { getPromotions } from '@/app/(protected)/marketing-management/promotions/services/promotionService';
import { getPackingLists } from '@/app/(protected)/procurement-management/packing-lists/services/packingListService';
import { linkAttachmentToPackingList, deleteAttachmentLink, unlinkPackingListFromAttachment } from '../services/attachmentService';
import { useContactAccessTypes } from '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes';

const ENTITY_ROUTES = {
  product: { label: 'Product', path: '/master-data-management/products' },
  promotion: { label: 'Promotion', path: '/marketing-management/promotions' },
  form: { label: 'Form', path: '/forms-management/forms' },
  packing_list: { label: 'Packing List', path: '/procurement-management/packing-lists' },
} as const;

function LinkagesTable({
  type,
  items,
  emptyMessage,
  onUnlink,
  onLink,
  attachmentId,
  refetch,
}: {
  type: keyof typeof ENTITY_ROUTES;
  items: LinkedEntityRef[];
  emptyMessage: string;
  onUnlink?: (item: LinkedEntityRef) => void;
  onLink?: () => void;
  attachmentId: string;
  refetch: () => void;
}) {
  const hasLinkId = type === 'product' || type === 'promotion';
  const canUnlink = hasLinkId ? (item: LinkedEntityRef) => !!item.link_id : (item: LinkedEntityRef) => true;
  const canUnlinkPackingList = true;
  const [manageFieldLinksFor, setManageFieldLinksFor] = useState<string | null>(null);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        {items.length > 0 ? null : <p className="text-sm text-muted-foreground">{emptyMessage}</p>}
        {onLink && (
          <Button variant="outline" size="sm" onClick={onLink}>
            <Plus className="size-4" />
            Link
          </Button>
        )}
      </div>
      {items.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Description</TableHead>
              <TableHead className="w-[180px]">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-medium">{item.name}</TableCell>
                <TableCell className="text-muted-foreground max-w-md line-clamp-2" title={item.description ?? undefined}>
                  {item.description ?? '—'}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <Link
                      href={`${ENTITY_ROUTES[type].path}/${item.id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary hover:underline inline-flex items-center gap-1 text-sm"
                    >
                      View
                      <ExternalLink className="size-3.5 shrink-0" />
                    </Link>
                    {type === 'product' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setManageFieldLinksFor(item.id)}
                        title="Manage field links"
                        data-testid={`linkages-manage-field-links-${item.id}`}
                      >
                        <SlidersHorizontal className="size-3.5" />
                        Fields
                      </Button>
                    )}
                    {onUnlink && (type === 'packing_list' ? canUnlinkPackingList : canUnlink(item)) && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => onUnlink(item)}
                      >
                        <Unlink className="size-3.5" />
                        Unlink
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {type === 'product' && manageFieldLinksFor && (
        <ManageFieldLinksDialog
          open={!!manageFieldLinksFor}
          onOpenChange={(open) => !open && setManageFieldLinksFor(null)}
          productId={manageFieldLinksFor}
          attachmentId={attachmentId}
          onSaved={() => {
            setManageFieldLinksFor(null);
            refetch();
          }}
        />
      )}
    </div>
  );
}

function LinkagesTabs({
  attachment,
  onRefetch,
  defaultAccessLevels = ['dealer', 'end_user'],
}: {
  attachment: Attachment;
  onRefetch: () => void;
  defaultAccessLevels?: string[];
}) {
  const queryClient = useQueryClient();
  const [linkDialogTab, setLinkDialogTab] = useState<keyof typeof ENTITY_ROUTES | null>(null);
  const [linkProductId, setLinkProductId] = useState('');
  const [linkPromotionId, setLinkPromotionId] = useState('');
  const [linkFormId, setLinkFormId] = useState('');
  const [linkPackingListId, setLinkPackingListId] = useState('');

  const products = attachment.linked_products ?? [];
  const promotions = attachment.linked_promotions ?? [];
  const form = attachment.linked_form ?? null;
  const packingLists = attachment.linked_packing_lists ?? [];

  const createProductLink = useCreateProductAttachment();
  const deleteProductLink = useDeleteProductAttachment();
  const createPromotionLink = useCreatePromotionAttachment();
  const deletePromotionLink = useDeletePromotionAttachment();
  const updateFormMutation = useUpdateForm();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['attachment-metadata', attachment.id] });
    queryClient.invalidateQueries({ queryKey: ['attachments'] });
    queryClient.invalidateQueries({ queryKey: ['product-attachments'] });
    queryClient.invalidateQueries({ queryKey: ['promotion-attachments'] });
    queryClient.invalidateQueries({ queryKey: ['forms'] });
    onRefetch();
  };

  const [unlinkPackingListPending, setUnlinkPackingListPending] = useState(false);
  const handleUnlinkPackingList = (item: LinkedEntityRef) => {
    setUnlinkPackingListPending(true);
    const promise = item.link_id
      ? deleteAttachmentLink(item.link_id, 'inbound_shipment')
      : unlinkPackingListFromAttachment(attachment.id, item.id);
    promise
      .then(() => invalidate())
      .finally(() => setUnlinkPackingListPending(false));
  };

  const [linkPackingListPending, setLinkPackingListPending] = useState(false);
  const handleLinkPackingList = () => {
    if (!linkPackingListId || !attachment.id) return;
    setLinkPackingListPending(true);
    linkAttachmentToPackingList(attachment.id, linkPackingListId)
      .then(() => {
        invalidate();
        setLinkDialogTab(null);
        setLinkPackingListId('');
      })
      .finally(() => setLinkPackingListPending(false));
  };

  const handleUnlinkProduct = (item: LinkedEntityRef) => {
    if (!item.link_id) return;
    deleteProductLink.mutate(item.link_id, {
      onSuccess: () => invalidate(),
    });
  };

  const handleUnlinkPromotion = (item: LinkedEntityRef) => {
    if (!item.link_id) return;
    deletePromotionLink.mutate(item.link_id, {
      onSuccess: () => invalidate(),
    });
  };

  const handleUnlinkForm = (item: LinkedEntityRef) => {
    updateFormMutation.mutate(
      { id: item.id, data: { attachment_id: null } },
      { onSuccess: () => invalidate() }
    );
  };

  const handleLinkProduct = () => {
    if (!linkProductId || !attachment.id) return;
    createProductLink.mutate(
      { product_id: linkProductId, attachment_id: attachment.id, access_levels: defaultAccessLevels },
      {
        onSuccess: () => {
          invalidate();
          setLinkDialogTab(null);
          setLinkProductId('');
        },
      }
    );
  };

  const handleLinkPromotion = () => {
    if (!linkPromotionId || !attachment.id) return;
    createPromotionLink.mutate(
      { promotion_id: linkPromotionId, attachment_id: attachment.id },
      {
        onSuccess: () => {
          invalidate();
          setLinkDialogTab(null);
          setLinkPromotionId('');
        },
      }
    );
  };

  const handleLinkForm = () => {
    if (!linkFormId || !attachment.id) return;
    updateFormMutation.mutate(
      { id: linkFormId, data: { attachment_id: attachment.id } },
      {
        onSuccess: () => {
          invalidate();
          setLinkDialogTab(null);
          setLinkFormId('');
        },
      }
    );
  };

  return (
    <>
      <Tabs defaultValue="products" className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="products">
            Products {products.length > 0 && `(${products.length})`}
          </TabsTrigger>
          <TabsTrigger value="promotions">
            Promotions {promotions.length > 0 && `(${promotions.length})`}
          </TabsTrigger>
          <TabsTrigger value="forms">
            Forms {form ? '(1)' : ''}
          </TabsTrigger>
          <TabsTrigger value="packing_lists">
            Packing Lists {packingLists.length > 0 && `(${packingLists.length})`}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="products" className="mt-4">
          <LinkagesTable
            type="product"
            items={products}
            emptyMessage="No products linked to this attachment."
            onUnlink={handleUnlinkProduct}
            onLink={() => setLinkDialogTab('product')}
            attachmentId={attachment.id}
            refetch={onRefetch}
          />
        </TabsContent>
        <TabsContent value="promotions" className="mt-4">
          <LinkagesTable
            type="promotion"
            items={promotions}
            emptyMessage="No promotions linked to this attachment."
            onUnlink={handleUnlinkPromotion}
            onLink={() => setLinkDialogTab('promotion')}
            attachmentId={attachment.id}
            refetch={onRefetch}
          />
        </TabsContent>
        <TabsContent value="forms" className="mt-4">
          <LinkagesTable
            type="form"
            items={form ? [form] : []}
            emptyMessage="No form linked to this attachment."
            onUnlink={form ? handleUnlinkForm : undefined}
            onLink={!form ? () => setLinkDialogTab('form') : undefined}
            attachmentId={attachment.id}
            refetch={onRefetch}
          />
        </TabsContent>
        <TabsContent value="packing_lists" className="mt-4">
          <LinkagesTable
            type="packing_list"
            items={packingLists}
            emptyMessage="No packing lists linked to this attachment."
            onUnlink={handleUnlinkPackingList}
            onLink={() => setLinkDialogTab('packing_list')}
            attachmentId={attachment.id}
            refetch={onRefetch}
          />
        </TabsContent>
      </Tabs>

      {/* Link dialogs */}
      <Dialog open={linkDialogTab === 'product'} onOpenChange={(o) => !o && setLinkDialogTab(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Link Product</DialogTitle>
          </DialogHeader>
          <LinkProductForm
            attachmentId={attachment.id}
            linkedProductIds={products.map((p) => p.id)}
            selectedId={linkProductId}
            onSelect={setLinkProductId}
            onSubmit={handleLinkProduct}
            onCancel={() => setLinkDialogTab(null)}
            isPending={createProductLink.isPending}
          />
        </DialogContent>
      </Dialog>
      <Dialog open={linkDialogTab === 'promotion'} onOpenChange={(o) => !o && setLinkDialogTab(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Link Promotion</DialogTitle>
          </DialogHeader>
          <LinkPromotionForm
            attachmentId={attachment.id}
            linkedPromotionIds={promotions.map((p) => p.id)}
            selectedId={linkPromotionId}
            onSelect={setLinkPromotionId}
            onSubmit={handleLinkPromotion}
            onCancel={() => setLinkDialogTab(null)}
            isPending={createPromotionLink.isPending}
          />
        </DialogContent>
      </Dialog>
      <Dialog open={linkDialogTab === 'form'} onOpenChange={(o) => !o && setLinkDialogTab(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Link Form</DialogTitle>
          </DialogHeader>
          <LinkFormForm
            attachmentId={attachment.id}
            selectedId={linkFormId}
            onSelect={setLinkFormId}
            onSubmit={handleLinkForm}
            onCancel={() => setLinkDialogTab(null)}
            isPending={updateFormMutation.isPending}
          />
        </DialogContent>
      </Dialog>
      <Dialog open={linkDialogTab === 'packing_list'} onOpenChange={(o) => !o && setLinkDialogTab(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Link Packing List</DialogTitle>
          </DialogHeader>
          <LinkPackingListForm
            attachmentId={attachment.id}
            linkedPackingListIds={packingLists.map((p) => p.id)}
            selectedId={linkPackingListId}
            onSelect={setLinkPackingListId}
            onSubmit={handleLinkPackingList}
            onCancel={() => setLinkDialogTab(null)}
            isPending={linkPackingListPending}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}

function LinkProductForm({
  attachmentId,
  linkedProductIds,
  selectedId,
  onSelect,
  onSubmit,
  onCancel,
  isPending,
}: {
  attachmentId: string;
  linkedProductIds: string[];
  selectedId: string;
  onSelect: (id: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [pickedLabel, setPickedLabel] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    if (!selectedId) setPickedLabel(null);
  }, [selectedId]);
  const { data, isFetching } = useQuery({
    queryKey: ['products-for-link', attachmentId, debounced],
    queryFn: () => getProducts({ pageIndex: 0, pageSize: 25, sorting: [], searchQuery: debounced }),
  });
  const products = (data?.data ?? []).filter((p) => !linkedProductIds.includes(p.id));
  const selectedFromList = products.find((p) => p.id === selectedId);
  const selectedLabel = selectedFromList
    ? (selectedFromList.product_name || selectedFromList.product_code || selectedFromList.id)
    : pickedLabel;

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Product</Label>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              mode="input"
              placeholder={!selectedLabel}
              aria-expanded={open}
              className="w-full justify-between"
            >
              {selectedLabel ?? 'Select a product...'}
              <ChevronDown className="ms-2 size-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-(--radix-popper-anchor-width) p-0" align="start">
            <Command shouldFilter={false}>
              <CommandInput
                placeholder="Search product..."
                value={search}
                onValueChange={setSearch}
              />
              <CommandList>
                <CommandEmpty>{isFetching ? 'Searching…' : 'No product found.'}</CommandEmpty>
                <CommandGroup>
                  {products.map((p) => {
                    const label = p.product_name || p.product_code || p.id;
                    return (
                      <CommandItem
                        key={p.id}
                        value={p.id}
                        onSelect={() => {
                          onSelect(p.id);
                          setPickedLabel(label);
                          setOpen(false);
                        }}
                      >
                        {label}
                        {selectedId === p.id && <CommandCheck />}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={onSubmit} disabled={!selectedId || isPending}>
          {isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : <Link2 className="size-4" />}
          Link
        </Button>
      </div>
    </div>
  );
}

function LinkPromotionForm({
  attachmentId,
  linkedPromotionIds,
  selectedId,
  onSelect,
  onSubmit,
  onCancel,
  isPending,
}: {
  attachmentId: string;
  linkedPromotionIds: string[];
  selectedId: string;
  onSelect: (id: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [pickedLabel, setPickedLabel] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    if (!selectedId) setPickedLabel(null);
  }, [selectedId]);
  const { data, isFetching } = useQuery({
    queryKey: ['promotions-for-link', attachmentId, debounced],
    queryFn: () => getPromotions({ pageIndex: 0, pageSize: 25, sorting: [], searchQuery: debounced }),
  });
  const promotions = (data?.data ?? []).filter((p) => !linkedPromotionIds.includes(p.id));
  const selectedFromList = promotions.find((p) => p.id === selectedId);
  const selectedLabel = selectedFromList
    ? (selectedFromList.name || selectedFromList.id)
    : pickedLabel;

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Promotion</Label>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              mode="input"
              placeholder={!selectedLabel}
              aria-expanded={open}
              className="w-full justify-between"
            >
              {selectedLabel ?? 'Select a promotion...'}
              <ChevronDown className="ms-2 size-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-(--radix-popper-anchor-width) p-0" align="start">
            <Command shouldFilter={false}>
              <CommandInput
                placeholder="Search promotion..."
                value={search}
                onValueChange={setSearch}
              />
              <CommandList>
                <CommandEmpty>{isFetching ? 'Searching…' : 'No promotion found.'}</CommandEmpty>
                <CommandGroup>
                  {promotions.map((p) => {
                    const label = p.name || p.id;
                    return (
                      <CommandItem
                        key={p.id}
                        value={p.id}
                        onSelect={() => {
                          onSelect(p.id);
                          setPickedLabel(label);
                          setOpen(false);
                        }}
                      >
                        {label}
                        {selectedId === p.id && <CommandCheck />}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={onSubmit} disabled={!selectedId || isPending}>
          {isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : <Link2 className="size-4" />}
          Link
        </Button>
      </div>
    </div>
  );
}

function LinkFormForm({
  attachmentId,
  selectedId,
  onSelect,
  onSubmit,
  onCancel,
  isPending,
}: {
  attachmentId: string;
  selectedId: string;
  onSelect: (id: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [pickedLabel, setPickedLabel] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    if (!selectedId) setPickedLabel(null);
  }, [selectedId]);
  const { data, isFetching } = useForms({ pageIndex: 0, pageSize: 25, sorting: [], searchQuery: debounced });
  const forms = (data?.data ?? []).filter((f) => f.attachment_id !== attachmentId);
  const selectedFromList = forms.find((f) => f.id === selectedId);
  const selectedLabel = selectedFromList
    ? (selectedFromList.name || selectedFromList.code || selectedFromList.id)
    : pickedLabel;

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Form</Label>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              mode="input"
              placeholder={!selectedLabel}
              aria-expanded={open}
              className="w-full justify-between"
            >
              {selectedLabel ?? 'Select a form...'}
              <ChevronDown className="ms-2 size-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-(--radix-popper-anchor-width) p-0" align="start">
            <Command shouldFilter={false}>
              <CommandInput
                placeholder="Search form..."
                value={search}
                onValueChange={setSearch}
              />
              <CommandList>
                <CommandEmpty>{isFetching ? 'Searching…' : 'No form found.'}</CommandEmpty>
                <CommandGroup>
                  {forms.map((f) => {
                    const label = f.name || f.code || f.id;
                    return (
                      <CommandItem
                        key={f.id}
                        value={f.id}
                        onSelect={() => {
                          onSelect(f.id);
                          setPickedLabel(label);
                          setOpen(false);
                        }}
                      >
                        {label}
                        {selectedId === f.id && <CommandCheck />}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={onSubmit} disabled={!selectedId || isPending}>
          {isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : <Link2 className="size-4" />}
          Link
        </Button>
      </div>
    </div>
  );
}

function LinkPackingListForm({
  attachmentId,
  linkedPackingListIds,
  selectedId,
  onSelect,
  onSubmit,
  onCancel,
  isPending,
}: {
  attachmentId: string;
  linkedPackingListIds: string[];
  selectedId: string;
  onSelect: (id: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [pickedLabel, setPickedLabel] = useState<string | null>(null);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 250);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(() => {
    if (!selectedId) setPickedLabel(null);
  }, [selectedId]);
  const { data, isFetching } = useQuery({
    queryKey: ['packing-lists-for-link', attachmentId, debounced],
    queryFn: () => getPackingLists({ pageIndex: 0, pageSize: 25, sorting: [], searchQuery: debounced }),
  });
  const packingLists = (data?.data ?? []).filter((p) => !linkedPackingListIds.includes(p.id));
  const selectedFromList = packingLists.find((p) => p.id === selectedId);
  const selectedLabel = selectedFromList
    ? (selectedFromList.shipment_number || selectedFromList.id)
    : pickedLabel;

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Packing List</Label>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              role="combobox"
              mode="input"
              placeholder={!selectedLabel}
              aria-expanded={open}
              className="w-full justify-between"
            >
              {selectedLabel ?? 'Select a packing list...'}
              <ChevronDown className="ms-2 size-4 shrink-0 opacity-50" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-(--radix-popper-anchor-width) p-0" align="start">
            <Command shouldFilter={false}>
              <CommandInput
                placeholder="Search packing list..."
                value={search}
                onValueChange={setSearch}
              />
              <CommandList>
                <CommandEmpty>{isFetching ? 'Searching…' : 'No packing list found.'}</CommandEmpty>
                <CommandGroup>
                  {packingLists.map((p) => {
                    const label = p.shipment_number || p.id;
                    return (
                      <CommandItem
                        key={p.id}
                        value={p.id}
                        onSelect={() => {
                          onSelect(p.id);
                          setPickedLabel(label);
                          setOpen(false);
                        }}
                      >
                        {label}
                        {selectedId === p.id && <CommandCheck />}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={onSubmit} disabled={!selectedId || isPending}>
          {isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : <Link2 className="size-4" />}
          Link
        </Button>
      </div>
    </div>
  );
}

interface AttachmentDetailModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  attachmentId: string | null;
  /** Current page attachments for prev/next navigation. When provided with onAttachmentChange, chevron nav is shown. */
  neighbourItems?: Array<{ id: string }>;
  /** Called when user clicks prev/next to switch attachment in modal. */
  onAttachmentChange?: (id: string) => void;
}

function getPreviewUrl(attachment: Attachment): string {
  const fp = attachment.file_path || '';
  if (fp.startsWith('http://') || fp.startsWith('https://')) return fp;
  if (typeof window === 'undefined') return '';
  return `${window.location.origin}/api/v1/resource-management/attachments/${attachment.id}/download`;
}

export default function AttachmentDetailModal({
  open,
  onOpenChange,
  attachmentId,
  neighbourItems = [],
  onAttachmentChange,
}: AttachmentDetailModalProps) {
  const queryClient = useQueryClient();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [descriptionEdit, setDescriptionEdit] = useState<string | null>(null);
  const [accessLevelsEdit, setAccessLevelsEdit] = useState<string[] | null>(null);
  const [editAttachmentTypeOpen, setEditAttachmentTypeOpen] = useState(false);

  const { data: accessTypeOptions = [] } = useContactAccessTypes();
  const defaultAccessLevels = accessTypeOptions.length > 0 ? accessTypeOptions.map((o) => o.code) : ['dealer', 'end_user'];
  const codeToName = Object.fromEntries(accessTypeOptions.map((o) => [o.code, o.name || o.code]));

  const { data: attachment, isLoading } = useQuery({
    queryKey: ['attachment-metadata', attachmentId],
    queryFn: () => getAttachmentMetadata(attachmentId!),
    enabled: !!attachmentId && open,
    retry: 1,
  });

  useEffect(() => {
    setDescriptionEdit(null);
    setAccessLevelsEdit(null);
  }, [attachmentId]);

  const downloadMutation = useDownloadAttachment();
  const resubmitMutation = useResubmitAttachmentWebhook();
  const restoreMutation = useRestoreAttachment();
  const updateMutation = useUpdateAttachment();

  const formatFileSize = (bytes: number | null | undefined) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const handleDownload = async (file: Attachment) => {
    try {
      const blob = await downloadMutation.mutateAsync(file.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.original_filename || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      // handled by toast
    }
  };

  const handlePreview = (att: Attachment) => {
    window.open(getPreviewUrl(att), '_blank', 'noopener,noreferrer');
  };

  const handleClose = () => {
    onOpenChange(false);
    queryClient.invalidateQueries({ queryKey: ['attachments'] });
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col overflow-hidden p-0">
          <DialogHeader className="px-6 pt-6 pb-0 pr-12 flex flex-row items-center justify-between gap-4">
            <DialogTitle className="text-xl truncate min-w-0 flex-1">
              {attachment?.original_filename ?? (isLoading ? 'Loading...' : 'Attachment')}
            </DialogTitle>
            {neighbourItems.length > 0 && onAttachmentChange && attachmentId && (
              <RecordNavigation
                basePath=""
                currentId={attachmentId}
                items={neighbourItems}
                ariaLabel="attachment"
                onSelect={onAttachmentChange}
              />
            )}
          </DialogHeader>
          <div className="flex-1 min-h-0 overflow-y-auto px-6 pb-6">
            {isLoading ? (
              <div className="space-y-4 py-6">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-32 w-full" />
                <Skeleton className="h-32 w-full" />
              </div>
            ) : !attachment ? (
              <p className="py-8 text-muted-foreground text-center">Attachment not found</p>
            ) : (
              <div className="space-y-6 py-6">
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePreview(attachment)}
                    title="Preview in new tab"
                  >
                    <Eye className="size-4" />
                    Preview
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDownload(attachment)}
                    disabled={downloadMutation.isPending}
                  >
                    <Download className="size-4" />
                    Download
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => resubmitMutation.mutate(attachment.id)}
                    disabled={resubmitMutation.isPending || attachment.is_deleted}
                  >
                    <RefreshCw className={`size-4 ${resubmitMutation.isPending ? 'animate-spin' : ''}`} />
                    Resubmit
                  </Button>
                  {attachment.is_deleted ? (
                    <>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => restoreMutation.mutate(attachment.id)}
                        disabled={restoreMutation.isPending}
                      >
                        Restore
                      </Button>
                      <Button variant="destructive" size="sm" onClick={() => setDeleteDialogOpen(true)}>
                        <Trash2 className="size-4" />
                        Permanently Delete
                      </Button>
                    </>
                  ) : (
                    <Button variant="destructive" size="sm" onClick={() => setDeleteDialogOpen(true)}>
                      <Trash2 className="size-4" />
                      Move to Trash
                    </Button>
                  )}
                </div>

                <Card>
                  <CardHeader className="py-4">
                    <CardTitle className="text-base">Attachment Details</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4 pt-0">
                    <div>
                      <p className="text-sm text-muted-foreground">Directory</p>
                      <p className="font-medium text-sm break-words">
                        {attachment.full_directory_path?.trim() || '—'}
                      </p>
                      {attachment.directory_id ? (
                        <a
                          href={`/resource-management/attachment-directories?directoryId=${attachment.directory_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline text-xs mt-1 inline-block"
                        >
                          Open folder →
                        </a>
                      ) : null}
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <p className="text-sm text-muted-foreground">File Type</p>
                        <p className="font-medium">{attachment.mime_type || '-'}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Attachment Type</p>
                        <div className="flex items-center justify-between gap-2">
                          <p className="font-medium">
                            {attachment.attachment_type?.type_name ?? '-'}
                          </p>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-primary"
                            onClick={() => setEditAttachmentTypeOpen(true)}
                            data-testid="attachment-type-edit"
                          >
                            Edit
                          </Button>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">File Size</p>
                        <p className="font-medium">{formatFileSize(attachment.file_size_bytes)}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Uploaded By</p>
                        <p className="font-medium">
                          {attachment.uploaded_by_user?.name ??
                            attachment.uploaded_by_user?.email ??
                            attachment.uploaded_by ??
                            '-'}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Uploaded</p>
                        <p className="font-medium">{formatDate(new Date(attachment.uploaded_at))}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Status</p>
                        <Badge
                          variant={attachment.is_deleted ? 'destructive' : 'success'}
                          appearance="ghost"
                        >
                          <BadgeDot />
                          {attachment.is_deleted ? 'Deleted' : 'Active'}
                        </Badge>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-sm text-muted-foreground">Description</Label>
                      {descriptionEdit !== null ? (
                        <div className="space-y-2">
                          <textarea
                            className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                            value={descriptionEdit}
                            onChange={(e) => setDescriptionEdit(e.target.value)}
                            placeholder="Add a description..."
                          />
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              onClick={() => {
                                updateMutation.mutate(
                                  { attachmentId: attachment.id, data: { description: descriptionEdit || null } },
                                  {
                                    onSuccess: () => {
                                      queryClient.invalidateQueries({ queryKey: ['attachment-metadata', attachment.id] });
                                      setDescriptionEdit(null);
                                    },
                                  }
                                );
                              }}
                              disabled={updateMutation.isPending}
                            >
                              {updateMutation.isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : 'Save'}
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => setDescriptionEdit(null)}>
                              Cancel
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-start justify-between gap-2">
                          <p className="font-medium text-sm min-h-[1.5rem]">
                            {attachment.description?.trim() || '—'}
                          </p>
                          <Button variant="ghost" size="sm" onClick={() => setDescriptionEdit(attachment.description ?? '')}>
                            {attachment.description?.trim() ? 'Edit' : 'Add'}
                          </Button>
                        </div>
                      )}
                    </div>
                    <div className="space-y-2">
                      <Label className="text-sm text-muted-foreground">Access levels</Label>
                      {accessLevelsEdit !== null ? (
                        <div className="space-y-2">
                          <div className="flex flex-wrap gap-4">
                            {accessTypeOptions.map((opt) => (
                              <label key={opt.code} className="flex items-center gap-2 cursor-pointer">
                                <Checkbox
                                  checked={accessLevelsEdit.includes(opt.code)}
                                  onCheckedChange={(checked) => {
                                    setAccessLevelsEdit((prev) => {
                                      const arr = prev ?? [];
                                      if (checked) return arr.includes(opt.code) ? arr : [...arr, opt.code];
                                      return arr.filter((v) => v !== opt.code);
                                    });
                                  }}
                                />
                                <span className="text-sm">{opt.name || opt.code}</span>
                              </label>
                            ))}
                          </div>
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              onClick={() => {
                                const levels = accessLevelsEdit?.length ? accessLevelsEdit : defaultAccessLevels;
                                updateMutation.mutate(
                                  { attachmentId: attachment.id, data: { access_levels: levels } },
                                  {
                                    onSuccess: () => {
                                      queryClient.invalidateQueries({ queryKey: ['attachment-metadata', attachment.id] });
                                      setAccessLevelsEdit(null);
                                    },
                                  }
                                );
                              }}
                              disabled={updateMutation.isPending}
                            >
                              {updateMutation.isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : 'Save'}
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => setAccessLevelsEdit(null)}>
                              Cancel
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex flex-wrap gap-2">
                            {(attachment.access_levels ?? []).length === 0 ? (
                              <span className="text-sm text-muted-foreground">—</span>
                            ) : (
                              (attachment.access_levels ?? []).map((level) => (
                                <Badge key={level} variant="secondary">
                                  {codeToName[level] ?? level}
                                </Badge>
                              ))
                            )}
                          </div>
                          <Button variant="ghost" size="sm" onClick={() => setAccessLevelsEdit(attachment.access_levels ?? defaultAccessLevels)}>
                            Edit
                          </Button>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="py-4">
                    <CardTitle className="text-base">Linkages</CardTitle>
                  </CardHeader>
                  <CardContent className="pt-0">
                    <LinkagesTabs attachment={attachment} onRefetch={() => queryClient.invalidateQueries({ queryKey: ['attachments'] })} defaultAccessLevels={defaultAccessLevels} />
                  </CardContent>
                </Card>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {attachment && (
        <AttachmentDeleteDialog
          open={deleteDialogOpen}
          onOpenChange={setDeleteDialogOpen}
          attachment={attachment}
          permanent={attachment.is_deleted}
          onSuccess={() => {
            onOpenChange(false);
            queryClient.invalidateQueries({ queryKey: ['attachments'] });
          }}
        />
      )}
      {attachment && (
        <EditAttachmentTypeDialog
          open={editAttachmentTypeOpen}
          onOpenChange={setEditAttachmentTypeOpen}
          attachmentIds={[attachment.id]}
          initialAttachmentTypeId={attachment.attachment_type_id ?? null}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ['attachment-metadata', attachment.id] });
            queryClient.invalidateQueries({ queryKey: ['attachments'] });
          }}
        />
      )}
    </>
  );
}
