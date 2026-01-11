import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

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

    const totalCount = await prisma.warehouse.count();

    const warehouses = await prisma.warehouse.findMany({
      skip: (page - 1) * limit,
      take: limit,
      include: {
        _count: {
          select: {
            storageZones: true,
            stock: true,
          },
        },
      },
    });

    // Transform to snake_case for frontend
    const transformedWarehouses = warehouses.map((w) => ({
      id: w.id,
      warehouse_code: w.warehouseCode,
      warehouse_name: w.warehouseName,
      location: w.location,
      manager_id: w.managerId,
      is_active: w.isActive,
      created_at: w.createdAt,
      updated_at: w.updatedAt,
      zones_count: w._count?.storageZones || 0,
    }));

    return NextResponse.json({
      data: transformedWarehouses,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching warehouses:', error);
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

    const warehouse = await prisma.warehouse.create({
      data: {
        warehouseCode: body.warehouse_code,
        warehouseName: body.warehouse_name,
        location: body.location || null,
        managerId: body.manager_id || null,
        isActive: body.is_active !== false,
      },
    });

    // Transform to snake_case for frontend
    const transformedWarehouse = {
      id: warehouse.id,
      warehouse_code: warehouse.warehouseCode,
      warehouse_name: warehouse.warehouseName,
      location: warehouse.location,
      manager_id: warehouse.managerId,
      is_active: warehouse.isActive,
      created_at: warehouse.createdAt,
      updated_at: warehouse.updatedAt,
    };

    return NextResponse.json(transformedWarehouse, { status: 201 });
  } catch (error) {
    console.error('Error creating warehouse:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
