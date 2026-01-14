import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

export async function POST(
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

    const line = await prisma.pickingLine.create({
      data: {
        pickingHeaderId: id,
        spoAllocationId: body.spo_allocation_id || null,
        productId: body.product_id,
        quantityExpected: body.quantity_expected,
        quantityPicked: body.quantity_picked,
        uomId: body.uom_id || null,
        pickedCondition: body.picked_condition || 'good',
        conditionRemarks: body.condition_remarks || null,
        batchNumberPicked: body.batch_number_picked || null,
        expiryDate: body.expiry_date ? new Date(body.expiry_date) : null,
        unitCost: body.unit_cost || null,
        lineTotal: body.line_total || null,
        sourceWarehouseId: body.source_warehouse_id || null,
        destinationWarehouseId: body.destination_warehouse_id || null,
      },
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
    });

    return NextResponse.json(
      {
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
            }
          : undefined,
      },
      { status: 201 },
    );
  } catch (error) {
    console.error('Error creating GRN line:', error);
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
    const lineId = body.line_id;

    if (!lineId) {
      return NextResponse.json(
        { message: 'Line ID is required' },
        { status: 400 },
      );
    }

    const line = await prisma.pickingLine.update({
      where: { id: lineId, pickingHeaderId: id },
      data: {
        spoAllocationId: body.spo_allocation_id || null,
        productId: body.product_id,
        quantityExpected: body.quantity_expected,
        quantityPicked: body.quantity_picked,
        uomId: body.uom_id || null,
        pickedCondition: body.picked_condition || 'good',
        conditionRemarks: body.condition_remarks || null,
        batchNumberPicked: body.batch_number_picked || null,
        expiryDate: body.expiry_date ? new Date(body.expiry_date) : null,
        unitCost: body.unit_cost || null,
        lineTotal: body.line_total || null,
        sourceWarehouseId: body.source_warehouse_id || null,
        destinationWarehouseId: body.destination_warehouse_id || null,
      },
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
    });

    return NextResponse.json({
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
          }
        : undefined,
    });
  } catch (error) {
    console.error('Error updating GRN line:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to update not found')
    ) {
      return NextResponse.json(
        { message: 'GRN line not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

export async function DELETE(
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
    const { searchParams } = new URL(request.url);
    const lineId = searchParams.get('line_id');

    if (!lineId) {
      return NextResponse.json(
        { message: 'Line ID is required' },
        { status: 400 },
      );
    }

    await prisma.pickingLine.delete({
      where: { id: lineId, pickingHeaderId: id },
    });

    return NextResponse.json({
      message: 'GRN line deleted successfully',
    });
  } catch (error) {
    console.error('Error deleting GRN line:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to delete does not exist')
    ) {
      return NextResponse.json(
        { message: 'GRN line not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
