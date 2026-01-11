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

    const totalCount = await prisma.marketingCampaign.count();

    const campaigns = await prisma.marketingCampaign.findMany({
      skip: (page - 1) * limit,
      take: limit,
      include: {
        campaignType: true,
      },
      orderBy: {
        createdAt: 'desc',
      },
    });

    return NextResponse.json({
      data: campaigns,
      pagination: {
        total: totalCount,
        page,
        limit,
      },
      empty: totalCount === 0,
    });
  } catch (error) {
    console.error('Error fetching campaigns:', error);
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

    const campaign = await prisma.marketingCampaign.create({
      data: {
        campaignCode: body.campaign_code,
        campaignName: body.campaign_name,
        campaignTypeId: body.campaign_type_id,
        description: body.description || null,
        startDate: new Date(body.start_date),
        endDate: body.end_date ? new Date(body.end_date) : null,
        budget: body.budget ? parseFloat(body.budget) : null,
        targetAudience: body.target_audience || null,
        status: body.status || 'PLANNING',
        createdBy: session.user?.id || null,
      },
      include: {
        campaignType: true,
      },
    });

    return NextResponse.json(campaign, { status: 201 });
  } catch (error) {
    console.error('Error creating campaign:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
