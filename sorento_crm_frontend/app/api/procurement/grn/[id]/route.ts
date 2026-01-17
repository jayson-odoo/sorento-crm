import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import type { Prisma } from '@prisma/client';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma picking header to frontend expected format (snake_case)
 */
function transformGRN(grn: any) {
  return {
    id: grn.id,
    picking_number: grn.pickingNumber,
    picking_type: grn.pickingType,
    source_entity_type: grn.sourceEntityType,
    source_entity_id: grn.sourceEntityId,
    picking_date: grn.pickingDate,
    picked_by_user_id: grn.pickedByUserId,
    inspection_status: grn.inspectionStatus,
    quality_remarks: grn.qualityRemarks,
    inspected_by_user_id: grn.inspectedByUserId,
    inspection_date: grn.inspectionDate,
    picking_status: grn.pickingStatus,
    total_items_picked: grn.totalItemsPicked,
    total_items_discrepancy: grn.totalItemsDiscrepancy,
    total_cost: grn.totalCost ? Number(grn.totalCost) : null,
    notes: grn.notes,
    created_at: grn.createdAt,
    updated_at: grn.updatedAt,
    picking_lines: grn.pickingLines
      ? grn.pickingLines.map((line: any) => ({
          id: line.id,
          picking_header_id: line.pickingHeaderId,
          spo_allocation_id: line.spoAllocationId,
          product_id: line.productId,
          quantity_expected: line.quantityExpected,
          quantity_picked: line.quantityPicked,
          quantity_discrepancy: line.quantityDiscrepancy,
          uom_id: line.uomId,
          picked_condition: line.pickedCondition,
          condition_remarks: line.conditionRemarks,
          batch_number_picked: line.batchNumberPicked,
          expiry_date: line.expiryDate,
          unit_cost: line.unitCost ? Number(line.unitCost) : null,
          line_total: line.lineTotal ? Number(line.lineTotal) : null,
          source_warehouse_id: line.sourceWarehouseId,
          destination_warehouse_id: line.destinationWarehouseId,
          product: line.product
            ? {
                id: line.product.id,
                product_code: line.product.productCode,
                product_name: line.product.productName,
              }
            : undefined,
          spo_allocation: line.spoAllocation
            ? {
                id: line.spoAllocation.id,
                spo_number: line.spoAllocation.spoNumber,
                inbound_shipment_id: line.spoAllocation.inboundShipmentId,
                inbound_shipment: line.spoAllocation.inboundShipment
                  ? {
                      id: line.spoAllocation.inboundShipment.id,
                      shipment_number:
                        line.spoAllocation.inboundShipment.shipmentNumber,
                    }
                  : undefined,
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

    const grn = await prisma.pickingHeader.findUnique({
      where: { id },
      include: {
        pickingLines: {
          include: {
            product: {
              select: {
                id: true,
                productCode: true,
                productName: true,
              },
            },
            spoAllocation: {
              select: {
                id: true,
                spoNumber: true,
                inboundShipmentId: true,
                inboundShipment: {
                  select: {
                    id: true,
                    shipmentNumber: true,
                  },
                },
              },
            },
          },
          orderBy: {
            createdAt: 'asc',
          },
        },
      },
    });

    if (!grn) {
      return NextResponse.json(
        { message: 'GRN not found' },
        { status: 404 },
      );
    }

    // Transform to snake_case for frontend
    const transformedGRN = transformGRN(grn);

    return NextResponse.json(transformedGRN);
  } catch (error) {
    console.error('Error fetching GRN:', error);
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

    // Update GRN header and lines in a transaction
    const grn = await prisma.$transaction(async (tx: Prisma.TransactionClient) => {
      // Update header
      await tx.pickingHeader.update({
        where: { id },
        data: {
          pickingNumber: body.picking_number,
          sourceEntityType: body.source_entity_type || null,
          sourceEntityId: body.source_entity_id || null,
          pickingDate: body.picking_date
            ? new Date(body.picking_date)
            : undefined,
          pickedByUserId: body.picked_by_user_id || null,
          inspectionStatus: body.inspection_status,
          qualityRemarks: body.quality_remarks || null,
          inspectedByUserId: body.inspected_by_user_id || null,
          inspectionDate: body.inspection_date
            ? new Date(body.inspection_date)
            : null,
          pickingStatus: body.picking_status,
          totalItemsPicked: body.total_items_picked || null,
          totalItemsDiscrepancy: body.total_items_discrepancy || null,
          totalCost: body.total_cost || null,
          notes: body.notes || null,
        },
      });

      // Update lines if provided
      if (body.picking_lines && Array.isArray(body.picking_lines)) {
        // Delete existing lines
        await tx.pickingLine.deleteMany({
          where: { pickingHeaderId: id },
        });

        // Create new lines
        if (body.picking_lines.length > 0) {
          await tx.pickingLine.createMany({
            data: body.picking_lines.map((line: any) => ({
              pickingHeaderId: id,
              spoAllocationId: line.spo_allocation_id || null,
              productId: line.product_id,
              quantityExpected: line.quantity_expected,
              quantityPicked: line.quantity_picked,
              uomId: line.uom_id || null,
              pickedCondition: line.picked_condition || 'good',
              conditionRemarks: line.condition_remarks || null,
              batchNumberPicked: line.batch_number_picked || null,
              expiryDate: line.expiry_date ? new Date(line.expiry_date) : null,
              unitCost: line.unit_cost || null,
              lineTotal: line.line_total || null,
              sourceWarehouseId: line.source_warehouse_id || null,
              destinationWarehouseId: line.destination_warehouse_id || null,
            })),
          });
        }
      }

      // Fetch the complete GRN with relations
      return await tx.pickingHeader.findUnique({
        where: { id },
        include: {
          pickingLines: {
            include: {
              product: {
                select: {
                  id: true,
                  productCode: true,
                  productName: true,
                },
              },
              spoAllocation: {
                select: {
                  id: true,
                  spoNumber: true,
                },
              },
            },
          },
        },
      });
    });

    // Transform to snake_case for frontend
    const transformedGRN = transformGRN(grn);

    return NextResponse.json(transformedGRN);
  } catch (error) {
    console.error('Error updating GRN:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to update not found')
    ) {
      return NextResponse.json(
        { message: 'GRN not found' },
        { status: 404 },
      );
    }

    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        {
          message:
            'Picking number already exists. Please use a different number.',
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

    // Delete GRN (cascade will delete lines)
    await prisma.pickingHeader.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'GRN deleted successfully' });
  } catch (error) {
    console.error('Error deleting GRN:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to delete does not exist')
    ) {
      return NextResponse.json(
        { message: 'GRN not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
