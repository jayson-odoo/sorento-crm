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

    // Get all trackings for metrics calculation
    const allTrackings = await prisma.conversationSLATracking.findMany({
      include: {
        policy: {
          select: {
            id: true,
            code: true,
            name: true,
          },
        },
      },
    });

    const totalTrackings = allTrackings.length;
    const resolvedCount = allTrackings.filter((t) => t.isResolved).length;
    const pendingCount = allTrackings.filter((t) => !t.isResolved && !t.escalatedAt).length;
    const escalatedCount = allTrackings.filter((t) => t.escalatedAt).length;

    // Calculate average resolution time (in hours)
    const resolvedTrackings = allTrackings.filter((t) => t.isResolved && t.resolutionDuration);
    const averageResolutionTime = resolvedTrackings.length > 0
      ? resolvedTrackings.reduce((sum, t) => sum + Number(t.resolutionDuration || 0), 0) / resolvedTrackings.length
      : 0;

    // Calculate escalation rate
    const escalationRate = totalTrackings > 0 ? (escalatedCount / totalTrackings) * 100 : 0;

    // Response time trends (last 30 days)
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
    
    const recentTrackings = allTrackings.filter((t) => new Date(t.initiatedAt) >= thirtyDaysAgo);
    const responseTimeTrends = Array.from({ length: 30 }, (_, i) => {
      const date = new Date();
      date.setDate(date.getDate() - (29 - i));
      const dateStr = date.toISOString().split('T')[0];
      
      const dayTrackings = recentTrackings.filter((t) => {
        const trackingDate = new Date(t.initiatedAt).toISOString().split('T')[0];
        return trackingDate === dateStr;
      });
      
      const avgResponseTime = dayTrackings.length > 0
        ? dayTrackings.reduce((sum, t) => {
            const duration = t.resolutionDuration ? Number(t.resolutionDuration) : 0;
            return sum + duration;
          }, 0) / dayTrackings.length
        : 0;
      
      return {
        date: dateStr,
        average_response_time: avgResponseTime,
      };
    });

    // Escalation rates by tier
    const escalationByTier = allTrackings.reduce((acc, t) => {
      if (t.escalatedAt) {
        acc[t.currentTier] = (acc[t.currentTier] || 0) + 1;
      }
      return acc;
    }, {} as Record<number, number>);

    const escalationRatesByTier = Object.entries(escalationByTier).map(([tierLevel, count]) => ({
      tier_level: parseInt(tierLevel, 10),
      escalation_count: count,
    }));

    // Resolution time distribution
    const resolutionTimeDistribution = {
      resolved: resolvedCount,
      unresolved: totalTrackings - resolvedCount,
    };

    // Status breakdown
    const statusBreakdown = {
      resolved: resolvedCount,
      escalated: escalatedCount,
      pending: pendingCount,
    };

    return NextResponse.json({
      total_trackings: totalTrackings,
      resolved_count: resolvedCount,
      pending_count: pendingCount,
      escalated_count: escalatedCount,
      average_resolution_time: averageResolutionTime,
      escalation_rate: escalationRate,
      response_time_trends: responseTimeTrends,
      escalation_rates_by_tier: escalationRatesByTier,
      resolution_time_distribution: resolutionTimeDistribution,
      status_breakdown: statusBreakdown,
    });
  } catch (error) {
    console.error('Error fetching SLA tracking dashboard metrics:', error);
    return NextResponse.json(
      { message: 'Oops! Something went wrong. Please try again in a moment.' },
      { status: 500 },
    );
  }
}
