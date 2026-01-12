import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma warehouse to frontend expected format (snake_case)
 */
function transformWarehouse(warehouse: any) {
  return {
    id: warehouse.id,
    warehouse_code: warehouse.warehouseCode,
    warehouse_name: warehouse.warehouseName,
    location: warehouse.location,
    manager_id: warehouse.managerId,
    is_active: warehouse.isActive,
    created_at: warehouse.createdAt,
    updated_at: warehouse.updatedAt,
  };
}

/**
 * GET /api/inventory/warehouses/:id
 * 
 * Fetch a single warehouse by ID
 */
export async function GET(
  request: Request,
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

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid warehouse ID format' },
        { status: 400 },
      );
    }

    const warehouse = await prisma.warehouse.findUnique({
      where: { id },
    });

    if (!warehouse) {
      return NextResponse.json(
        { message: 'Warehouse not found' },
        { status: 404 },
      );
    }

    return NextResponse.json(transformWarehouse(warehouse));
  } catch (error) {
    console.error('Error fetching warehouse:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

/**
 * PUT /api/inventory/warehouses/:id
 * 
 * Update a warehouse
 */
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

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid warehouse ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const warehouse = await prisma.warehouse.update({
      where: { id },
      data: {
        warehouseCode: body.warehouse_code,
        warehouseName: body.warehouse_name,
        location: body.location || null,
        managerId: body.manager_id || null,
        isActive: body.is_active !== false,
      },
    });

    return NextResponse.json(transformWarehouse(warehouse));
  } catch (error) {
    console.error('Error updating warehouse:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

/**
 * DELETE /api/inventory/warehouses/:id
 * 
 * Delete (soft delete) a warehouse by setting isActive to false
 */
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

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid warehouse ID format' },
        { status: 400 },
      );
    }

    // Check if warehouse has zones
    const zones = await prisma.storageZone.findMany({
      where: { warehouseId: id },
    });
    if (zones.length > 0) {
      return NextResponse.json(
        { message: 'Warehouse has zones and cannot be deleted' },
        { status: 400 },
      );
    }

    // Delete the warehouse
    await prisma.warehouse.delete({
      where: { id },
    });

    return NextResponse.json({ message: 'Warehouse deactivated successfully' });
  } catch (error) {
    console.error('Error deleting warehouse:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
