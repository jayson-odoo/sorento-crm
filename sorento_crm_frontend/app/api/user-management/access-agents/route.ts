import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma access agent to frontend expected format (snake_case)
 */
function transformAccessAgent(agent: any) {
  return {
    id: agent.id,
    code: agent.code,
    name: agent.name,
    description: agent.description,
    is_active: agent.isActive,
    created_at: agent.createdAt,
    updated_at: agent.updatedAt,
    synced_to_excel: agent.syncedToExcel,
    last_synced_to_excel: agent.lastSyncedToExcel,
    pic_respond_user_id: agent.picRespondUserId,
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

    const totalCount = await prisma.accessAgent.count({ where: whereClause });

    // Map sort field
    const sortMap: Record<string, string> = {
      code: 'code',
      name: 'name',
      created_at: 'createdAt',
      updated_at: 'updatedAt',
    };
    const mappedSortField = sortMap[sortField] || 'createdAt';

    const agents = await prisma.accessAgent.findMany({
      where: whereClause,
      skip: (page - 1) * limit,
      take: limit,
      include: {
        _count: {
          select: {
            contactAccesses: true,
          },
        },
      },
      orderBy: { [mappedSortField]: sortDirection },
    });

    // Transform to snake_case for frontend
    const transformedAgents = agents.map((agent) => ({
      ...transformAccessAgent(agent),
      contact_accesses_count: agent._count?.contactAccesses || 0,
    }));

    return NextResponse.json({
      data: transformedAgents,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching access agents:', error);
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

    const agent = await prisma.accessAgent.create({
      data: {
        code: body.code,
        name: body.name,
        description: body.description || null,
        picRespondUserId: body.pic_respond_user_id || null,
        isActive: body.is_active !== false,
      },
    });

    // Transform to snake_case for frontend
    const transformedAgent = transformAccessAgent(agent);

    return NextResponse.json(transformedAgent, { status: 201 });
  } catch (error) {
    console.error('Error creating access agent:', error);
    
    // Handle unique constraint violation
    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        { message: 'Access agent code already exists. Please use a different code.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
