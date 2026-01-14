import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma SPO allocation to frontend expected format (snake_case)
 */
function transformSPOAllocation(allo: any) {
  return {
    id: allo.id,
    spo_number: allo.spoNumber,
    spo_line_number: allo.spoLineNumber,
    inbound_shipment_lines_id: allo.inboundShipmentLinesId,
    inbound_shipment_id: allo.inboundShipmentId,
    warehouse_id: allo.warehouseId,
    storage_zone_id: allo.storageZoneId,
    allocated_quantity: allo.allocatedQuantity,
    uom_id: allo.uomId,
    receipt_status: allo.receiptStatus,
    quantity_received: allo.quantityReceived,
    quantity_rejected: allo.quantityRejected,
    allocation_notes: allo.allocationNotes,
    created_at: allo.createdAt,
    created_by: allo.createdBy,
    product_id: allo.productId,
    synced_to_excel: allo.syncedToExcel,
    updated_at: allo.updatedAt,
    last_synced_to_excel: allo.lastSyncedToExcel,
    inbound_shipment: allo.inboundShipment
      ? {
          id: allo.inboundShipment.id,
          shipment_number: allo.inboundShipment.shipmentNumber,
        }
      : undefined,
    warehouse: allo.warehouse
      ? {
          id: allo.warehouse.id,
          warehouse_code: allo.warehouse.warehouseCode,
          warehouse_name: allo.warehouse.warehouseName,
        }
      : undefined,
    product: allo.product
      ? {
          id: allo.product.id,
          product_code: allo.product.productCode,
          product_name: allo.product.productName,
        }
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

    const allocation = await prisma.sPOAllocation.findUnique({
      where: { id },
      include: {
        inboundShipment: {
          select: {
            id: true,
            shipmentNumber: true,
          },
        },
        warehouse: {
          select: {
            id: true,
            warehouseCode: true,
            warehouseName: true,
          },
        },
        product: {
          select: {
            id: true,
            productCode: true,
            productName: true,
          },
        },
        _count: {
          select: {
            pickingLines: true,
          },
        },
      },
    });

    if (!allocation) {
      return NextResponse.json(
        { message: 'SPO allocation not found' },
        { status: 404 },
      );
    }

    // Transform to snake_case for frontend
    const transformedAllocation = {
      ...transformSPOAllocation(allocation),
      grn_lines_count: allocation._count?.pickingLines || 0,
    };

    return NextResponse.json(transformedAllocation);
  } catch (error) {
    console.error('Error fetching SPO allocation:', error);
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

    const allocation = await prisma.sPOAllocation.update({
      where: { id },
      data: {
        spoNumber: body.spo_number || null,
        spoLineNumber: body.spo_line_number || null,
        inboundShipmentLinesId: body.inbound_shipment_lines_id || null,
        inboundShipmentId: body.inbound_shipment_id,
        warehouseId: body.warehouse_id,
        storageZoneId: body.storage_zone_id || null,
        allocatedQuantity: body.allocated_quantity,
        uomId: body.uom_id || null,
        receiptStatus: body.receipt_status,
        quantityReceived: body.quantity_received || 0,
        quantityRejected: body.quantity_rejected || 0,
        allocationNotes: body.allocation_notes || null,
        productId: body.product_id,
      },
      include: {
        inboundShipment: {
          select: {
            id: true,
            shipmentNumber: true,
          },
        },
        warehouse: {
          select: {
            id: true,
            warehouseCode: true,
            warehouseName: true,
          },
        },
        product: {
          select: {
            id: true,
            productCode: true,
            productName: true,
          },
        },
      },
    });

    // Transform to snake_case for frontend
    const transformedAllocation = transformSPOAllocation(allocation);

    return NextResponse.json(transformedAllocation);
  } catch (error) {
    console.error('Error updating SPO allocation:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to update not found')
    ) {
      return NextResponse.json(
        { message: 'SPO allocation not found' },
        { status: 404 },
      );
    }

    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        {
          message:
            'SPO number and line number combination already exists. Please use a different combination.',
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

    await prisma.sPOAllocation.delete({
      where: { id },
    });

    return NextResponse.json({
      message: 'SPO allocation deleted successfully',
    });
  } catch (error) {
    console.error('Error deleting SPO allocation:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to delete does not exist')
    ) {
      return NextResponse.json(
        { message: 'SPO allocation not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
