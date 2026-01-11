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
    const query = searchParams.get('query') || '';
    const sortField = searchParams.get('sort') || 'created_at';
    const sortDirection = searchParams.get('dir') === 'desc' ? 'desc' : 'asc';

    const whereClause: any = {
      ...(query ? {
        OR: [
          { uomCode: { contains: query, mode: 'insensitive' } },
          { uomName: { contains: query, mode: 'insensitive' } },
        ],
      } : {}),
    };

    const sortMap: Record<string, any> = {
      'created_at': 'createdAt',
      'uom_code': 'uomCode',
      'uom_name': 'uomName',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const totalCount = await prisma.unitOfMeasure.count({ where: whereClause });

    const uoms = await prisma.unitOfMeasure.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      orderBy: { [mappedSortField]: sortDirection },
      include: {
        baseUom: true,
      },
    });

    const transformedUOMs = uoms.map((uom) => ({
      id: uom.id,
      uom_code: uom.uomCode,
      uom_name: uom.uomName,
      base_uom_id: uom.baseUomId,
      conversion_factor: uom.conversionFactor ? Number(uom.conversionFactor) : null,
      description: uom.description,
      created_at: uom.createdAt,
      updated_at: uom.updatedAt,
      base_uom: uom.baseUom ? {
        id: uom.baseUom.id,
        uom_code: uom.baseUom.uomCode,
        uom_name: uom.baseUom.uomName,
      } : undefined,
    }));

    return NextResponse.json({
      data: transformedUOMs,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching UOMs:', error);
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

    const uom = await prisma.unitOfMeasure.create({
      data: {
        uomCode: body.uom_code,
        uomName: body.uom_name,
        baseUomId: body.base_uom_id || null,
        conversionFactor: body.conversion_factor || null,
        description: body.description || null,
      },
    });

    return NextResponse.json(uom, { status: 201 });
  } catch (error) {
    console.error('Error creating UOM:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
