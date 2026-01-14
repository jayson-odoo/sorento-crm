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

export async function GET(req: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const { searchParams } = new URL(req.url);
    const page = parseInt(searchParams.get('page') || '1', 10);
    const limit = parseInt(searchParams.get('limit') || '50', 10);
    const query = searchParams.get('query') || '';
    const sortField = searchParams.get('sort') || 'created_at';
    const sortDirection = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';
    const supplierId = searchParams.get('supplier_id') || null;
    const shipmentStatus = searchParams.get('shipment_status') || null;

    // Build where clause with filters
    const whereClause: any = {
      ...(supplierId && supplierId !== 'all' ? { supplierId } : {}),
      ...(shipmentStatus && shipmentStatus !== 'all'
        ? { shipmentStatus }
        : {}),
      ...(query
        ? {
            OR: [
              { shipmentNumber: { contains: query, mode: 'insensitive' } },
              { billOfLadingNumber: { contains: query, mode: 'insensitive' } },
              { shippingContainerNumber: { contains: query, mode: 'insensitive' } },
              { invoiceNumber: { contains: query, mode: 'insensitive' } },
              {
                supplier: {
                  supplierName: { contains: query, mode: 'insensitive' },
                },
              },
              {
                supplier: {
                  supplierCode: { contains: query, mode: 'insensitive' },
                },
              },
            ],
          }
        : {}),
    };

    const totalCount = await prisma.inboundShipment.count({ where: whereClause });

    // Map sort field
    const sortMap: Record<string, string> = {
      shipment_number: 'shipmentNumber',
      shipment_date: 'shipmentDate',
      created_at: 'createdAt',
      updated_at: 'updatedAt',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const shipments = await prisma.inboundShipment.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      include: {
        supplier: {
          select: {
            id: true,
            supplierCode: true,
            supplierName: true,
          },
        },
        _count: {
          select: {
            shipmentLines: true,
            spoAllocations: true,
          },
        },
      },
      orderBy: { [mappedSortField]: sortDirection },
    });

    // Transform to snake_case for frontend
    const transformedShipments = shipments.map((shipment) => ({
      ...transformPackingList(shipment),
      lines_count: shipment._count?.shipmentLines || 0,
      spo_allocations_count: shipment._count?.spoAllocations || 0,
    }));

    return NextResponse.json({
      data: transformedShipments,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching packing lists:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const session = await getServerSession(authOptions);

    if (!session) {
      return NextResponse.json(
        { message: 'Unauthorized request' },
        { status: 401 },
      );
    }

    const body = await request.json();

    // Create shipment with lines in a transaction
    const shipment = await prisma.$transaction(async (tx) => {
      const newShipment = await tx.inboundShipment.create({
        data: {
          shipmentNumber: body.shipment_number,
          supplierId: body.supplier_id,
          shipmentDate: body.shipment_date
            ? new Date(body.shipment_date)
            : new Date(),
          expectedArrivalDate: body.expected_arrival_date
            ? new Date(body.expected_arrival_date)
            : null,
          actualArrivalDate: body.actual_arrival_date
            ? new Date(body.actual_arrival_date)
            : null,
          billOfLadingNumber: body.bill_of_lading_number || null,
          shippingContainerNumber: body.shipping_container_number || null,
          invoiceNumber: body.invoice_number || null,
          shipmentStatus: body.shipment_status || 'in_transit',
          totalItemsShipped: body.total_items_shipped || null,
          totalCartons: body.total_cartons || null,
          notes: body.notes || null,
          createdBy: session.user?.id || null,
          attachmentId: body.attachment_id,
        },
      });

      // Create line items if provided
      if (body.shipment_lines && Array.isArray(body.shipment_lines)) {
        await tx.inboundShipmentLine.createMany({
          data: body.shipment_lines.map((line: any) => ({
            shipmentId: newShipment.id,
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

      // Fetch the complete shipment with relations
      return await tx.inboundShipment.findUnique({
        where: { id: newShipment.id },
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

    return NextResponse.json(transformedShipment, { status: 201 });
  } catch (error) {
    console.error('Error creating packing list:', error);

    // Handle unique constraint violation
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
