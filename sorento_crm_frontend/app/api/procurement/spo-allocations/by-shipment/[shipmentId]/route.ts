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
  { params }: { params: Promise<{ shipmentId: string }> },
) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { shipmentId } = await params;

    const allocations = await prisma.sPOAllocation.findMany({
      where: {
        inboundShipmentId: shipmentId,
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
        _count: {
          select: {
            pickingLines: true,
          },
        },
      },
      orderBy: {
        createdAt: 'asc',
      },
    });

    // Transform to snake_case for frontend
    const transformedAllocations = allocations.map((allo) => ({
      ...transformSPOAllocation(allo),
      grn_lines_count: allo._count?.pickingLines || 0,
    }));

    return NextResponse.json({
      data: transformedAllocations,
      pagination: {
        total: allocations.length,
        page: 1,
        limit: allocations.length,
      },
      empty: allocations.length === 0,
    });
  } catch (error) {
    console.error('Error fetching SPO allocations by shipment:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
