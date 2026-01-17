import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma SLA policy to frontend expected format (snake_case)
 */
function transformSLAPolicy(policy: any) {
  return {
    id: policy.id,
    code: policy.code,
    name: policy.name,
    description: policy.description,
    is_active: policy.isActive,
    created_at: policy.createdAt,
    updated_at: policy.updatedAt,
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
    const status = searchParams.get('status') || 'all';

    // Build where clause with filters
    const whereClause: any = {
      ...(status && status !== 'all'
        ? { isActive: status === 'active' }
        : {}),
      ...(query
        ? {
            OR: [
              { code: { contains: query, mode: 'insensitive' } },
              { name: { contains: query, mode: 'insensitive' } },
              { description: { contains: query, mode: 'insensitive' } },
            ],
          }
        : {}),
    };

    const totalCount = await prisma.sLAPolicy.count({ where: whereClause });

    // Map sort field
    const sortMap: Record<string, string> = {
      code: 'code',
      name: 'name',
      created_at: 'createdAt',
      updated_at: 'updatedAt',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const policies = await prisma.sLAPolicy.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      include: {
        _count: {
          select: {
            tiers: true,
            tracking: true,
          },
        },
      },
      orderBy: { [mappedSortField]: sortDirection },
    });

    // Transform to snake_case for frontend
    const transformedPolicies = policies.map((policy: {
      id: string;
      code: string;
      name: string;
      description: string | null;
      isActive: boolean;
      createdAt: Date;
      updatedAt: Date | null;
      _count?: { tiers: number; tracking: number };
    }) => ({
      ...transformSLAPolicy(policy),
      tiers_count: policy._count?.tiers || 0,
      tracking_count: policy._count?.tracking || 0,
    }));

    return NextResponse.json({
      data: transformedPolicies,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching SLA policies:', error);
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

    const policy = await prisma.sLAPolicy.create({
      data: {
        code: body.code,
        name: body.name,
        description: body.description || null,
        isActive: body.is_active !== false,
      },
    });

    // Transform to snake_case for frontend
    const transformedPolicy = transformSLAPolicy(policy);

    return NextResponse.json(transformedPolicy, { status: 201 });
  } catch (error) {
    console.error('Error creating SLA policy:', error);
    
    // Handle unique constraint violation
    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        { message: 'SLA policy code already exists. Please use a different code.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
