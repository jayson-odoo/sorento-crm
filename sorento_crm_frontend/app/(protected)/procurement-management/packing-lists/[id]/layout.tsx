'use client';

import React, { use, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useMutation } from '@tanstack/react-query';
import {
  Boxes,
  Download,
  Edit,
  FileSpreadsheet,
  FileText,
  Files,
  History,
  Info,
  Settings,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { formatDate } from '@/lib/helpers';
import { downloadPackingListExport } from '@/app/(protected)/scm/services/fulfilmentService';
import DetailActions from '@/components/common/DetailActions';
import BackToList from '@/components/common/BackToList';
import { packingListsPagerQuery } from '../hooks/usePackingLists';
import PackingListDeleteDialog from '../components/packing-list-delete-dialog';
import ContainerStatusImportDialog from '../components/ContainerStatusImportDialog';
import {
  PackingListProvider,
  usePackingListRecord,
} from './components/packing-list-context';

/**
 * The packing list reads like a user record: one toolbar over routed tabs.
 *
 * Same shape as `user-management/users/[id]` - Toolbar with prev/next, one primary action,
 * the occasional ones behind a gear, and a `TabsList variant="line"` whose tabs are ROUTES.
 * Routes rather than local state so a tab is linkable, survives a refresh and keeps its
 * place in the back button; the edit draft lives above them all in `PackingListProvider`,
 * because Edit is on this toolbar and Save is still ONE `PUT` for the whole record.
 */

const TAB_ORDER = [
  { key: 'details', title: 'Details', icon: Info, segment: '' },
  {
    key: 'proforma-invoices',
    title: 'Proforma invoices',
    icon: FileText,
    segment: 'proforma-invoices',
  },
  { key: 'lines', title: 'Shipment lines', icon: Boxes, segment: 'lines' },
  { key: 'documents', title: 'Documents', icon: Files, segment: 'documents' },
  { key: 'spo', title: 'SPO planner', icon: FileSpreadsheet, segment: 'spo' },
  { key: 'timeline', title: 'Timeline', icon: History, segment: 'timeline' },
] as const;

/** What the old `?tab=` values mean now, so a link somebody saved still lands. */
const LEGACY_TAB_SEGMENT: Record<string, string> = {
  timeline: 'timeline',
  details: '',
  documents: 'documents',
  lines: 'lines',
  spo: 'spo',
};

function PackingListToolbar({ id }: { id: string }) {
  const router = useRouter();
  const {
    packingList,
    isLoading,
    lineSupplierNames,
    editing,
    saving,
    beginEdit,
    cancelEdit,
    saveEdit,
  } = usePackingListRecord();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const exportWorkbook = useMutation({
    // The name the file falls back to is the container, never the shipment id: a workbook
    // in a downloads folder called after a UUID cannot be told from any other one.
    mutationFn: () =>
      downloadPackingListExport(
        id,
        packingList?.shipping_container_number ??
          packingList?.shipment_number ??
          'container',
      ),
    onError: (e: Error) => toast.error(e.message),
  });

  const title =
    packingList?.shipping_container_number ||
    packingList?.shipment_number ||
    'Packing list';

  const subtitle = packingList
    ? [
        packingList.supplier?.supplier_name || lineSupplierNames || 'No supplier',
        packingList.shipment_date
          ? `Shipment date ${formatDate(new Date(packingList.shipment_date))}`
          : null,
      ]
        .filter(Boolean)
        .join(' • ')
    : '';

  return (
    <>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle className="break-words">
            {isLoading ? <Skeleton className="h-6 w-48" /> : title}
          </ToolbarTitle>
          {/* Read-only metadata belongs in the header, never inside a tab body: it has no
              edit counterpart, and putting it in a tab would make view and edit differ. */}
          <p className="text-sm text-muted-foreground break-words">{subtitle}</p>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/procurement-management">Procurement</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/procurement-management/packing-lists">
                  Packing Lists
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>{title}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
        <ToolbarActions>
          <BackToList
            listPath="/procurement-management/packing-lists"
            label="Back to packing lists"
          />
        </ToolbarActions>
      </Toolbar>

      {/* The record's own actions: pager, gear, primary (D6). They sit under the
          toolbar rather than on it, and wrap under the title at 375. */}
      <div className="mb-5">
        {editing ? (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button onClick={() => void saveEdit()} disabled={saving}>
              Save
            </Button>
            <Button variant="outline" onClick={cancelEdit} disabled={saving}>
              <X className="size-4" />
              Cancel
            </Button>
          </div>
        ) : (
          <DetailActions
            pager={{
              ...packingListsPagerQuery,
              detailPath: '/procurement-management/packing-lists',
              currentId: id,
              ariaLabel: 'packing list',
            }}
            gearLabel="Packing list options"
            gear={
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="icon" aria-label="Packing list options">
                    <Settings className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={beginEdit} disabled={!packingList}>
                    <Edit className="size-4" />
                    Edit
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setImportOpen(true)}>
                    <Upload className="size-4" />
                    Import Container Status workbook
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    variant="destructive"
                    onClick={() => setDeleteOpen(true)}
                    disabled={!packingList}
                  >
                    <Trash2 className="size-4" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            }
            primary={
              <Button
                onClick={() => exportWorkbook.mutate()}
                disabled={exportWorkbook.isPending || !packingList}
              >
                <Download className="size-4" />
                Download packing list
              </Button>
            }
          />
        )}
      </div>

      {packingList && (
        <PackingListDeleteDialog
          open={deleteOpen}
          closeDialog={() => setDeleteOpen(false)}
          packingList={packingList}
          onSuccess={() => router.push('/procurement-management/packing-lists')}
        />
      )}
      <ContainerStatusImportDialog open={importOpen} onOpenChange={setImportOpen} />
    </>
  );
}

function PackingListTabs({ id }: { id: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const { packingList, isLoading } = usePackingListRecord();
  const base = `/procurement-management/packing-lists/${id}`;

  const active = useMemo(() => {
    const tail = pathname.startsWith(base) ? pathname.slice(base.length) : '';
    const segment = tail.replace(/^\//, '');
    return TAB_ORDER.find((t) => t.segment === segment)?.key ?? 'details';
  }, [pathname, base]);

  const lineCount = packingList?.shipment_lines?.length ?? 0;

  return (
    <Tabs value={active}>
      <TabsList variant="line" className="mb-5 w-full justify-start overflow-x-auto">
        {TAB_ORDER.map(({ key, title, icon: Icon, segment }) => (
          <TabsTrigger
            key={key}
            value={key}
            disabled={isLoading}
            onClick={() => router.push(segment ? `${base}/${segment}` : base)}
          >
            <Icon />
            <span>{title}</span>
            {key === 'lines' && lineCount > 0 ? (
              <Badge variant="secondary" className="ms-2">
                {lineCount}
              </Badge>
            ) : null}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}

/** `?tab=lines` used to be how a tab was linked. Those links still land on the right one. */
function LegacyTabRedirect({ id }: { id: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const base = `/procurement-management/packing-lists/${id}`;

  useEffect(() => {
    const requested = searchParams.get('tab');
    if (!requested || pathname !== base) return;
    const segment = LEGACY_TAB_SEGMENT[requested];
    if (segment === undefined) return;
    const params = new URLSearchParams(searchParams.toString());
    params.delete('tab');
    const qs = params.toString();
    router.replace(`${segment ? `${base}/${segment}` : base}${qs ? `?${qs}` : ''}`);
  }, [searchParams, pathname, base, router]);

  return null;
}

export default function PackingListLayout({
  params,
  children,
}: {
  params: Promise<{ id: string }>;
  children: React.ReactNode;
}) {
  const { id } = use(params);

  return (
    <PackingListProvider packingListId={id}>
      <Container>
        <LegacyTabRedirect id={id} />
        <PackingListToolbar id={id} />
        <PackingListTabs id={id} />
        {children}
      </Container>
    </PackingListProvider>
  );
}
