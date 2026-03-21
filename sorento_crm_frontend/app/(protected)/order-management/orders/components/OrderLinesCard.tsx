'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
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
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Trash2, Plus, Upload } from 'lucide-react';
import { useCreateOrderLine, useDeleteOrderLine } from '../hooks/useOrders';
import { importDeliveryOrderDetail } from '../services/orderService';
import type { OrderLine } from '../types/order.types';
import { toast } from 'sonner';
import OrderLineDeleteDialog from './OrderLineDeleteDialog';

interface OrderLinesCardProps {
  orderId: string;
  lines: OrderLine[];
}

export default function OrderLinesCard({ orderId, lines }: OrderLinesCardProps) {
  const queryClient = useQueryClient();
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [deleteLine, setDeleteLine] = useState<OrderLine | null>(null);
  const createLineMutation = useCreateOrderLine();

  const [formProductId, setFormProductId] = useState('');
  const [formWarehouseId, setFormWarehouseId] = useState('');
  const [formQuantity, setFormQuantity] = useState('');
  const [formUnitPrice, setFormUnitPrice] = useState('');
  const [formDiscount, setFormDiscount] = useState('');
  const [formTotal, setFormTotal] = useState('');
  const [formTax, setFormTax] = useState('');
  const [formTotalExcl, setFormTotalExcl] = useState('');
  const [formTotalIncl, setFormTotalIncl] = useState('');

  const handleAddLine = async () => {
    if (!formProductId.trim() || !formWarehouseId.trim()) {
      toast.error('Product and Warehouse are required');
      return;
    }
    try {
      await createLineMutation.mutateAsync({
        orderId,
        data: {
          product_id: formProductId.trim(),
          warehouse_id: formWarehouseId.trim(),
          quantity: formQuantity ? Number(formQuantity) : undefined,
          unit_price: formUnitPrice ? Number(formUnitPrice) : undefined,
          discount: formDiscount ? Number(formDiscount) : undefined,
          total: formTotal ? Number(formTotal) : undefined,
          tax: formTax ? Number(formTax) : undefined,
          total_excluding_tax: formTotalExcl ? Number(formTotalExcl) : undefined,
          total_including_tax: formTotalIncl ? Number(formTotalIncl) : undefined,
        },
      });
      setAddDialogOpen(false);
      setFormProductId('');
      setFormWarehouseId('');
      setFormQuantity('');
      setFormUnitPrice('');
      setFormDiscount('');
      setFormTotal('');
      setFormTax('');
      setFormTotalExcl('');
      setFormTotalIncl('');
    } catch {
      // toast from mutation
    }
  };

  const handleImport = async () => {
    if (!importFile) {
      toast.error('Select a file');
      return;
    }
    setImporting(true);
    try {
      await importDeliveryOrderDetail(importFile);
      queryClient.invalidateQueries({ queryKey: ['order', orderId] });
      queryClient.invalidateQueries({ queryKey: ['orders'] });
      toast.success('Import queued. Check System → Import jobs for status.');
      setImportDialogOpen(false);
      setImportFile(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  const formatNum = (v: number | string | null | undefined) =>
    v != null && v !== '' ? new Intl.NumberFormat('en-MY', { minimumFractionDigits: 2 }).format(Number(v)) : '-';

  return (
    <>
      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4 flex-wrap">
          <CardTitle>Order Lines (Delivery order detail)</CardTitle>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setImportDialogOpen(true)}>
              <Upload className="size-4 mr-1" />
              Import
            </Button>
            <Button variant="primary" size="sm" onClick={() => setAddDialogOpen(true)} disabled={createLineMutation.isPending}>
              <Plus className="size-4 mr-1" />
              Add line
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {lines.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">No order lines. Import from Excel or add manually.</p>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Product</TableHead>
                    <TableHead>Warehouse</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Unit price</TableHead>
                    <TableHead className="text-right">Discount</TableHead>
                    <TableHead className="text-right">Total</TableHead>
                    <TableHead className="text-right">Tax</TableHead>
                    <TableHead className="text-right">Total (excl)</TableHead>
                    <TableHead className="text-right">Total (incl)</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {lines.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell>
                        {line.product ? `${line.product.product_code ?? ''} - ${line.product.product_name ?? ''}` : line.product_id}
                      </TableCell>
                      <TableCell>
                        {line.warehouse ? `${line.warehouse.warehouse_code ?? ''} - ${line.warehouse.warehouse_name ?? ''}` : line.warehouse_id}
                      </TableCell>
                      <TableCell className="text-right">{formatNum(line.quantity)}</TableCell>
                      <TableCell className="text-right">{formatNum(line.unit_price)}</TableCell>
                      <TableCell className="text-right">{formatNum(line.discount)}</TableCell>
                      <TableCell className="text-right">{formatNum(line.total)}</TableCell>
                      <TableCell className="text-right">{formatNum(line.tax)}</TableCell>
                      <TableCell className="text-right">{formatNum(line.total_excluding_tax)}</TableCell>
                      <TableCell className="text-right">{formatNum(line.total_including_tax)}</TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setDeleteLine(line)}
                          aria-label="Delete line"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add order line</DialogTitle>
            <DialogDescription>Product ID and Warehouse ID are required (UUIDs from Products and Warehouses).</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Product ID</Label>
              <Input value={formProductId} onChange={(e) => setFormProductId(e.target.value)} placeholder="UUID" />
            </div>
            <div className="grid gap-2">
              <Label>Warehouse ID</Label>
              <Input value={formWarehouseId} onChange={(e) => setFormWarehouseId(e.target.value)} placeholder="UUID" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="grid gap-2">
                <Label>Quantity</Label>
                <Input type="number" value={formQuantity} onChange={(e) => setFormQuantity(e.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>Unit price</Label>
                <Input type="number" value={formUnitPrice} onChange={(e) => setFormUnitPrice(e.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="grid gap-2">
                <Label>Discount</Label>
                <Input type="number" value={formDiscount} onChange={(e) => setFormDiscount(e.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>Total</Label>
                <Input type="number" value={formTotal} onChange={(e) => setFormTotal(e.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="grid gap-2">
                <Label>Tax</Label>
                <Input type="number" value={formTax} onChange={(e) => setFormTax(e.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>Total (excl)</Label>
                <Input type="number" value={formTotalExcl} onChange={(e) => setFormTotalExcl(e.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label>Total (incl)</Label>
                <Input type="number" value={formTotalIncl} onChange={(e) => setFormTotalIncl(e.target.value)} />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleAddLine} disabled={createLineMutation.isPending}>Add</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Import order lines</DialogTitle>
            <DialogDescription>Upload Excel with columns: Doc No, Item Code, Location, Qty, Unit Price, Discount, Total, Tax, Total Excluding Tax, Total Including Tax.</DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Input
              type="file"
              accept=".xlsx,.xls"
              onChange={(e) => setImportFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setImportDialogOpen(false)}>Cancel</Button>
            <Button onClick={handleImport} disabled={!importFile || importing}>{importing ? 'Queuing…' : 'Import'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {deleteLine && (
        <OrderLineDeleteDialog
          open={!!deleteLine}
          onOpenChange={(open: boolean) => !open && setDeleteLine(null)}
          orderId={orderId}
          line={deleteLine}
          onSuccess={() => setDeleteLine(null)}
        />
      )}
    </>
  );
}
