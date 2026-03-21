'use client';

import { useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  getAllContactAccessTypes,
  createContactAccessType,
  updateContactAccessType,
  deleteContactAccessType,
  getAllRespondMappings,
  createRespondMapping,
  updateRespondMapping,
  deleteRespondMapping,
  type ContactAccessTypeAdmin,
  type RespondAccessTypeMappingAdmin,
} from '../services/contactAccessTypeService';
import { useContactAccessTypes } from '../hooks/useContactAccessTypes';

export default function ContactAccessTypesAdmin() {
  const queryClient = useQueryClient();
  const { data: options = [] } = useContactAccessTypes();
  const [catalogTab, setCatalogTab] = useState<'catalog' | 'mappings'>('catalog');

  const { data: types = [], isLoading: typesLoading } = useQuery({
    queryKey: ['contact-access-types-admin'],
    queryFn: getAllContactAccessTypes,
  });

  const { data: mappings = [], isLoading: mappingsLoading } = useQuery({
    queryKey: ['respond-access-type-mappings'],
    queryFn: getAllRespondMappings,
  });

  const createTypeMutation = useMutation({
    mutationFn: createContactAccessType,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact-access-types-admin'] });
      queryClient.invalidateQueries({ queryKey: ['contact-access-types'] });
      setTypeDialogOpen(false);
      resetTypeForm();
      toast.success('Access type created');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const updateTypeMutation = useMutation({
    mutationFn: ({ code, body }: { code: string; body: Parameters<typeof updateContactAccessType>[1] }) =>
      updateContactAccessType(code, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact-access-types-admin'] });
      queryClient.invalidateQueries({ queryKey: ['contact-access-types'] });
      setTypeDialogOpen(false);
      setEditingType(null);
      resetTypeForm();
      toast.success('Access type updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteTypeMutation = useMutation({
    mutationFn: deleteContactAccessType,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contact-access-types-admin'] });
      queryClient.invalidateQueries({ queryKey: ['contact-access-types'] });
      setDeleteTypeCode(null);
      toast.success('Access type deleted');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const createMappingMutation = useMutation({
    mutationFn: createRespondMapping,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['respond-access-type-mappings'] });
      setMappingDialogOpen(false);
      resetMappingForm();
      toast.success('Mapping created');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const updateMappingMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updateRespondMapping>[1] }) =>
      updateRespondMapping(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['respond-access-type-mappings'] });
      setMappingDialogOpen(false);
      setEditingMapping(null);
      resetMappingForm();
      toast.success('Mapping updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMappingMutation = useMutation({
    mutationFn: deleteRespondMapping,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['respond-access-type-mappings'] });
      setDeleteMappingId(null);
      toast.success('Mapping deleted');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const [typeDialogOpen, setTypeDialogOpen] = useState(false);
  const [editingType, setEditingType] = useState<ContactAccessTypeAdmin | null>(null);
  const [deleteTypeCode, setDeleteTypeCode] = useState<string | null>(null);
  const [typeForm, setTypeForm] = useState({
    code: '',
    name: '',
    description: '',
    is_active: true,
    sort_order: '' as string | number,
  });

  const [mappingDialogOpen, setMappingDialogOpen] = useState(false);
  const [editingMapping, setEditingMapping] = useState<RespondAccessTypeMappingAdmin | null>(null);
  const [deleteMappingId, setDeleteMappingId] = useState<string | null>(null);
  const [mappingForm, setMappingForm] = useState({
    source_key: '',
    access_type_code: '',
    is_active: true,
  });

  function resetTypeForm() {
    setTypeForm({
      code: '',
      name: '',
      description: '',
      is_active: true,
      sort_order: '',
    });
    setEditingType(null);
  }

  function resetMappingForm() {
    setMappingForm({
      source_key: '',
      access_type_code: options[0]?.code ?? '',
      is_active: true,
    });
    setEditingMapping(null);
  }

  function openCreateType() {
    resetTypeForm();
    setTypeDialogOpen(true);
  }

  function openEditType(row: ContactAccessTypeAdmin) {
    setEditingType(row);
    setTypeForm({
      code: row.code,
      name: row.name,
      description: row.description ?? '',
      is_active: row.is_active,
      sort_order: row.sort_order ?? '',
    });
    setTypeDialogOpen(true);
  }

  function saveType() {
    if (editingType) {
      const sort = typeForm.sort_order === '' ? undefined : Number(typeForm.sort_order);
      if (Number.isNaN(sort)) return;
      updateTypeMutation.mutate({
        code: editingType.code,
        body: {
          name: typeForm.name,
          description: typeForm.description || null,
          is_active: typeForm.is_active,
          sort_order: sort,
        },
      });
    } else {
      const sort = typeForm.sort_order === '' ? undefined : Number(typeForm.sort_order);
      if (!typeForm.code.trim() || !typeForm.name.trim()) {
        toast.error('Code and name are required');
        return;
      }
      if (typeForm.sort_order !== '' && Number.isNaN(Number(typeForm.sort_order))) return;
      createTypeMutation.mutate({
        code: typeForm.code.trim(),
        name: typeForm.name.trim(),
        description: typeForm.description.trim() || null,
        is_active: typeForm.is_active,
        sort_order: sort ?? null,
      });
    }
  }

  function openCreateMapping() {
    resetMappingForm();
    const firstCode = types[0]?.code ?? options[0]?.code ?? '';
    setMappingForm((prev) => ({
      ...prev,
      access_type_code: firstCode,
    }));
    setMappingDialogOpen(true);
  }

  function openEditMapping(row: RespondAccessTypeMappingAdmin) {
    setEditingMapping(row);
    setMappingForm({
      source_key: row.source_key,
      access_type_code: row.access_type_code,
      is_active: row.is_active,
    });
    setMappingDialogOpen(true);
  }

  function saveMapping() {
    if (editingMapping) {
      updateMappingMutation.mutate({
        id: editingMapping.id,
        body: {
          source_key: mappingForm.source_key.trim(),
          access_type_code: mappingForm.access_type_code,
          is_active: mappingForm.is_active,
        },
      });
    } else {
      if (!mappingForm.source_key.trim() || !mappingForm.access_type_code) {
        toast.error('Respond value and access type are required');
        return;
      }
      createMappingMutation.mutate({
        source_key: mappingForm.source_key.trim(),
        access_type_code: mappingForm.access_type_code,
        is_active: mappingForm.is_active,
      });
    }
  }

  return (
    <div className="space-y-6">
      <Tabs value={catalogTab} onValueChange={(v) => setCatalogTab(v as 'catalog' | 'mappings')}>
        <TabsList>
          <TabsTrigger value="catalog">Access type catalog</TabsTrigger>
          <TabsTrigger value="mappings">Respond mappings</TabsTrigger>
        </TabsList>

        <TabsContent value="catalog" className="mt-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle>Contact access types</CardTitle>
              <Button onClick={openCreateType}>
                <Plus className="size-4 mr-2" />
                Add type
              </Button>
            </CardHeader>
            <CardContent>
              {typesLoading ? (
                <Skeleton className="h-48 w-full" />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Code</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead>Sort order</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="w-[100px]">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {types.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="text-muted-foreground text-center">
                          No access types. Add one to get started.
                        </TableCell>
                      </TableRow>
                    ) : (
                      types.map((row) => (
                        <TableRow key={row.code}>
                          <TableCell className="font-mono">{row.code}</TableCell>
                          <TableCell>{row.name}</TableCell>
                          <TableCell className="max-w-[200px] truncate">
                            {row.description ?? '—'}
                          </TableCell>
                          <TableCell>{row.sort_order ?? '—'}</TableCell>
                          <TableCell>
                            {row.is_active ? (
                              <Badge variant="primary">Active</Badge>
                            ) : (
                              <Badge variant="secondary">Inactive</Badge>
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="flex gap-2">
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => openEditType(row)}
                                aria-label="Edit"
                              >
                                <Pencil className="size-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => setDeleteTypeCode(row.code)}
                                aria-label="Delete"
                              >
                                <Trash2 className="size-4 text-destructive" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="mappings" className="mt-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle>Respond value → Access type</CardTitle>
              <Button onClick={openCreateMapping} disabled={types.length === 0}>
                <Plus className="size-4 mr-2" />
                Add mapping
              </Button>
            </CardHeader>
            <CardContent>
              {types.length === 0 && (
                <p className="text-sm text-muted-foreground mb-4">
                  Add at least one access type in the catalog before creating mappings.
                </p>
              )}
              {mappingsLoading ? (
                <Skeleton className="h-48 w-full" />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Respond value (source_key)</TableHead>
                      <TableHead>Access type</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="w-[100px]">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {mappings.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} className="text-muted-foreground text-center">
                          No mappings. Add one to map Respond.io values to access types.
                        </TableCell>
                      </TableRow>
                    ) : (
                      mappings.map((row) => (
                        <TableRow key={row.id}>
                          <TableCell className="font-mono">{row.source_key}</TableCell>
                          <TableCell>{row.access_type_code}</TableCell>
                          <TableCell>
                            {row.is_active ? (
                              <Badge variant="primary">Active</Badge>
                            ) : (
                              <Badge variant="secondary">Inactive</Badge>
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="flex gap-2">
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => openEditMapping(row)}
                                aria-label="Edit"
                              >
                                <Pencil className="size-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => setDeleteMappingId(row.id)}
                                aria-label="Delete"
                              >
                                <Trash2 className="size-4 text-destructive" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Type create/edit dialog */}
      <Dialog open={typeDialogOpen} onOpenChange={setTypeDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingType ? 'Edit access type' : 'Add access type'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="type-code">Code</Label>
              <Input
                id="type-code"
                value={typeForm.code}
                onChange={(e) => setTypeForm((f) => ({ ...f, code: e.target.value }))}
                placeholder="e.g. dealer"
                disabled={!!editingType}
              />
              {editingType && (
                <p className="text-xs text-muted-foreground">Code cannot be changed after creation.</p>
              )}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="type-name">Name</Label>
              <Input
                id="type-name"
                value={typeForm.name}
                onChange={(e) => setTypeForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Dealer"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="type-desc">Description (optional)</Label>
              <Input
                id="type-desc"
                value={typeForm.description}
                onChange={(e) => setTypeForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="Optional description"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="type-sort">Sort order (optional)</Label>
              <Input
                id="type-sort"
                type="number"
                value={typeForm.sort_order}
                onChange={(e) =>
                  setTypeForm((f) => ({
                    ...f,
                    sort_order: e.target.value === '' ? '' : Number(e.target.value),
                  }))
                }
                placeholder="0"
              />
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="type-active"
                checked={typeForm.is_active}
                onCheckedChange={(v) => setTypeForm((f) => ({ ...f, is_active: v === true }))}
              />
              <Label htmlFor="type-active">Active</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTypeDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={saveType}
              disabled={
                createTypeMutation.isPending ||
                updateTypeMutation.isPending ||
                !typeForm.name.trim() ||
                (!editingType && !typeForm.code.trim())
              }
            >
              {editingType ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Mapping create/edit dialog */}
      <Dialog open={mappingDialogOpen} onOpenChange={setMappingDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingMapping ? 'Edit mapping' : 'Add mapping'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="map-source">Respond value (source_key)</Label>
              <Input
                id="map-source"
                value={mappingForm.source_key}
                onChange={(e) => setMappingForm((f) => ({ ...f, source_key: e.target.value }))}
                placeholder="e.g. Dealer or end_user"
              />
              <p className="text-xs text-muted-foreground">
                Raw value from Respond.io (e.g. custom field) that should map to the access type below.
              </p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="map-code">Access type</Label>
              <select
                id="map-code"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                value={mappingForm.access_type_code}
                onChange={(e) =>
                  setMappingForm((f) => ({ ...f, access_type_code: e.target.value }))
                }
              >
                {(types.length > 0 ? types : options.map((o) => ({ code: o.code, name: o.name }))).map(
                  (o) => (
                    <option key={o.code} value={o.code}>
                      {o.name} ({o.code})
                    </option>
                  )
                )}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="map-active"
                checked={mappingForm.is_active}
                onCheckedChange={(v) => setMappingForm((f) => ({ ...f, is_active: v === true }))}
              />
              <Label htmlFor="map-active">Active</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMappingDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={saveMapping}
              disabled={
                createMappingMutation.isPending ||
                updateMappingMutation.isPending ||
                !mappingForm.source_key.trim() ||
                !mappingForm.access_type_code
              }
            >
              {editingMapping ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete type confirmation */}
      <Dialog open={!!deleteTypeCode} onOpenChange={(open) => !open && setDeleteTypeCode(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete access type</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete the access type &quot;{deleteTypeCode}&quot;? This may
            affect contacts and content visibility.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTypeCode(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteTypeCode && deleteTypeMutation.mutate(deleteTypeCode)}
              disabled={deleteTypeMutation.isPending}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete mapping confirmation */}
      <Dialog open={!!deleteMappingId} onOpenChange={(open) => !open && setDeleteMappingId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete mapping</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete this Respond mapping?
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteMappingId(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteMappingId && deleteMappingMutation.mutate(deleteMappingId)}
              disabled={deleteMappingMutation.isPending}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
