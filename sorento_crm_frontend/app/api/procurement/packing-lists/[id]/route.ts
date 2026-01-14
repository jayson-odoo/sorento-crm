import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma inbound shipment to frontend expected format (snake_case)
 */
function transformPackingList(shipment: any) {
  return {
    id: shipment.id,
    shipment_number: shipment.shipmentNumber,
    supplier_id: shipment.supplierId,
    shipment_date: shipment.shipmentDate,
    expected_arrival_date: shipment.expectedArrivalDate,
    actual_arrival_date: shipment.actualArrivalDate,
    bill_of_lading_number: shipment.billOfLadingNumber,
    shipping_container_number: shipment.shippingContainerNumber,
    invoice_number: shipment.invoiceNumber,
    shipment_status: shipment.shipmentStatus,
    total_items_shipped: shipment.totalItemsShipped,
    total_cartons: shipment.totalCartons,
    notes: shipment.notes,
    created_at: shipment.createdAt,
    created_by: shipment.createdBy,
    updated_at: shipment.updatedAt,
    attachment_id: shipment.attachmentId,
    synced_to_excel: shipment.syncedToExcel,
    last_synced_to_excel: shipment.lastSyncedToExcel,
    supplier: shipment.supplier
      ? {
          id: shipment.supplier.id,
          supplier_code: shipment.supplier.supplierCode,
          supplier_name: shipment.supplier.supplierName,
        }
      : undefined,
    shipment_lines: shipment.shipmentLines
      ? shipment.shipmentLines.map((line: any) => ({
          id: line.id,
          shipment_id: line.shipmentId,
          product_id: line.productId,
          quantity_shipped: line.quantityShipped,
          uom_id: line.uomId,
          batch_number: line.batchNumber,
          serial_number_range_from: line.serialNumberRangeFrom,
          serial_number_range_to: line.serialNumberRangeTo,
          carton_number: line.cartonNumber,
          cartons_count: line.cartonsCount,
          weight_per_carton: line.weightPerCarton
            ? Number(line.weightPerCarton)
            : null,
          unit_cost: line.unitCost ? Number(line.unitCost) : null,
          product: line.product
            ? {
                id: line.product.id,
                product_code: line.product.productCode,
                product_name: line.product.productName,
              }
            : undefined,
        }))
      : undefined,
  };
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    const shipment = await prisma.inboundShipment.findUnique({
      where: { id },
      include: {
        supplier: {
          select: {
            id: true,
            supplierCode: true,
            supplierName: true,
          },
        },
        shipmentLines: {
          include: {
            product: {
              select: {
                id: true,
                productCode: true,
                productName: true,
              },
            },
          },
          orderBy: {
            createdAt: 'asc',
          },
        },
        _count: {
          select: {
            spoAllocations: true,
          },
        },
      },
    });

    if (!shipment) {
      return NextResponse.json(
        { message: 'Packing list not found' },
        { status: 404 },
      );
    }

    // Transform to snake_case for frontend
    const transformedShipment = {
      ...transformPackingList(shipment),
      spo_allocations_count: shipment._count?.spoAllocations || 0,
    };

    return NextResponse.json(transformedShipment);
  } catch (error) {
    console.error('Error fetching packing list:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;
    const body = await request.json();

    // Update shipment and lines in a transaction
    const shipment = await prisma.$transaction(async (tx) => {
      // Update header
      await tx.inboundShipment.update({
        where: { id },
        data: {
          shipmentNumber: body.shipment_number,
          supplierId: body.supplier_id,
          shipmentDate: body.shipment_date
            ? new Date(body.shipment_date)
            : undefined,
          expectedArrivalDate: body.expected_arrival_date
            ? new Date(body.expected_arrival_date)
            : null,
          actualArrivalDate: body.actual_arrival_date
            ? new Date(body.actual_arrival_date)
            : null,
          billOfLadingNumber: body.bill_of_lading_number || null,
          shippingContainerNumber: body.shipping_container_number || null,
          invoiceNumber: body.invoice_number || null,
          shipmentStatus: body.shipment_status,
          totalItemsShipped: body.total_items_shipped || null,
          totalCartons: body.total_cartons || null,
          notes: body.notes || null,
          attachmentId: body.attachment_id,
        },
      });

      // Update lines if provided
      if (body.shipment_lines && Array.isArray(body.shipment_lines)) {
        // Delete existing lines
        await tx.inboundShipmentLine.deleteMany({
          where: { shipmentId: id },
        });

        // Create new lines
        if (body.shipment_lines.length > 0) {
          await tx.inboundShipmentLine.createMany({
            data: body.shipment_lines.map((line: any) => ({
              shipmentId: id,
              productId: line.product_id,
              quantityShipped: line.quantity_shipped,
              uomId: line.uom_id || null,
              batchNumber: line.batch_number || null,
              serialNumberRangeFrom: line.serial_number_range_from || null,
              serialNumberRangeTo: line.serial_number_range_to || null,
              cartonNumber: line.carton_number || null,
              cartonsCount: line.cartons_count || 1,
              weightPerCarton: line.weight_per_carton || null,
              unitCost: line.unit_cost || null,
            })),
          });
        }
      }

      // Fetch the complete shipment with relations
      return await tx.inboundShipment.findUnique({
        where: { id },
        include: {
          supplier: {
            select: {
              id: true,
              supplierCode: true,
              supplierName: true,
            },
          },
          shipmentLines: {
            include: {
              product: {
                select: {
                  id: true,
                  productCode: true,
                  productName: true,
                },
              },
            },
          },
        },
      });
    });

    // Transform to snake_case for frontend
    const transformedShipment = transformPackingList(shipment);

    return NextResponse.json(transformedShipment);
  } catch (error) {
    console.error('Error updating packing list:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to update not found')
    ) {
      return NextResponse.json(
        { message: 'Packing list not found' },
        { status: 404 },
      );
    }

    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        {
          message:
            'Shipment number already exists. Please use a different number.',
        },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { id } = await params;

    // Delete shipment (cascade will delete lines)
    await prisma.inboundShipment.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'Packing list deleted successfully' });
  } catch (error) {
    console.error('Error deleting packing list:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to delete does not exist')
    ) {
      return NextResponse.json(
        { message: 'Packing list not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
