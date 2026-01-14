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

    const line = await prisma.inboundShipmentLine.create({
      data: {
        shipmentId: id,
        productId: body.product_id,
        quantityShipped: body.quantity_shipped,
        uomId: body.uom_id || null,
        batchNumber: body.batch_number || null,
        serialNumberRangeFrom: body.serial_number_range_from || null,
        serialNumberRangeTo: body.serial_number_range_to || null,
        cartonNumber: body.carton_number || null,
        cartonsCount: body.cartons_count || 1,
        weightPerCarton: body.weight_per_carton || null,
        unitCost: body.unit_cost || null,
      },
      include: {
        product: {
          select: {
            id: true,
            productCode: true,
            productName: true,
          },
        },
      },
    });

    return NextResponse.json(
      {
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
      },
      { status: 201 },
    );
  } catch (error) {
    console.error('Error creating packing list line:', error);
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

    const line = await prisma.inboundShipmentLine.update({
      where: { id: lineId, shipmentId: id },
      data: {
        productId: body.product_id,
        quantityShipped: body.quantity_shipped,
        uomId: body.uom_id || null,
        batchNumber: body.batch_number || null,
        serialNumberRangeFrom: body.serial_number_range_from || null,
        serialNumberRangeTo: body.serial_number_range_to || null,
        cartonNumber: body.carton_number || null,
        cartonsCount: body.cartons_count || 1,
        weightPerCarton: body.weight_per_carton || null,
        unitCost: body.unit_cost || null,
      },
      include: {
        product: {
          select: {
            id: true,
            productCode: true,
            productName: true,
          },
        },
      },
    });

    return NextResponse.json({
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
    });
  } catch (error) {
    console.error('Error updating packing list line:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to update not found')
    ) {
      return NextResponse.json(
        { message: 'Packing list line not found' },
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

    await prisma.inboundShipmentLine.delete({
      where: { id: lineId, shipmentId: id },
    });

    return NextResponse.json({
      message: 'Packing list line deleted successfully',
    });
  } catch (error) {
    console.error('Error deleting packing list line:', error);

    if (
      error instanceof Error &&
      error.message.includes('Record to delete does not exist')
    ) {
      return NextResponse.json(
        { message: 'Packing list line not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
