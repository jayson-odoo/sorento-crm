import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth/next';
import { prisma } from '@/lib/prisma';
import authOptions from '@/app/api/auth/[...nextauth]/auth-options';

/**
 * Transform Prisma SLA policy tier to frontend expected format (snake_case)
 */
function transformSLAPolicyTier(tier: any) {
  return {
    id: tier.id,
    policy_id: tier.policyId,
    tier_level: tier.tierLevel,
    tier_name: tier.tierName,
    response_hours: tier.responseHours,
    created_at: tier.createdAt,
    updated_at: tier.updatedAt,
  };
}

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
        { message: 'Invalid SLA policy ID format' },
        { status: 400 },
      );
    }

    const tiers = await prisma.sLAPolicyTier.findMany({
      where: { policyId: id },
      orderBy: {
        tierLevel: 'asc',
      },
    });

    // Transform to snake_case for frontend
    const transformedTiers = tiers.map(transformSLAPolicyTier);

    return NextResponse.json(transformedTiers);
  } catch (error) {
    console.error('Error fetching SLA policy tiers:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}

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

    // Validate that id is a valid UUID format
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      return NextResponse.json(
        { message: 'Invalid SLA policy ID format' },
        { status: 400 },
      );
    }

    const body = await request.json();

    const tier = await prisma.sLAPolicyTier.create({
      data: {
        policyId: id,
        tierLevel: body.tier_level,
        tierName: body.tier_name,
        responseHours: body.response_hours,
      },
    });

    // Transform to snake_case for frontend
    const transformedTier = transformSLAPolicyTier(tier);

    return NextResponse.json(transformedTier, { status: 201 });
  } catch (error) {
    console.error('Error creating SLA policy tier:', error);
    
    // Handle unique constraint violation
    if (error instanceof Error && error.message.includes('Unique constraint')) {
      return NextResponse.json(
        { message: 'Tier level already exists for this policy. Please use a different tier level.' },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
