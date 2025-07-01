import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

// Check if a video has already been processed
export const getProcessedVideo = query({
  args: { videoId: v.string() },
  handler: async (ctx, args) => {
    return await ctx.db
      .query("processedVideos")
      .withIndex("by_video_id", (q) => q.eq("videoId", args.videoId))
      .first();
  },
});

// Save processed video data
export const saveProcessedVideo = mutation({
  args: {
    videoId: v.string(),
    videoUrl: v.string(),
    title: v.optional(v.string()),
    speakers: v.array(v.object({
      id: v.string(),
      totalTime: v.number(),
      segmentCount: v.number(),
      avgSegmentLength: v.number(),
      segments: v.array(v.object({
        start: v.number(),
        end: v.number(),
      })),
    })),
    identifiedHost: v.string(),
    processingTime: v.number(),
    processingCost: v.number(),
  },
  handler: async (ctx, args) => {
    // Check if video already exists
    const existing = await ctx.db
      .query("processedVideos")
      .withIndex("by_video_id", (q) => q.eq("videoId", args.videoId))
      .first();
    
    if (existing) {
      // Update existing record
      return await ctx.db.patch(existing._id, {
        ...args,
        createdAt: Date.now(),
      });
    }
    
    // Create new record
    return await ctx.db.insert("processedVideos", {
      ...args,
      createdAt: Date.now(),
    });
  },
});

// Get all processed videos
export const getAllProcessedVideos = query({
  handler: async (ctx) => {
    return await ctx.db
      .query("processedVideos")
      .order("desc")
      .collect();
  },
});

// Get user statistics
export const getUserStats = query({
  handler: async (ctx) => {
    const stats = await ctx.db.query("userStats").first();
    if (!stats) {
      return {
        totalVideosProcessed: 0,
        totalProcessingTime: 0,
        totalCost: 0,
      };
    }
    return stats;
  },
});

// Update user statistics
export const updateUserStats = mutation({
  args: {
    processingTime: v.number(),
    cost: v.number(),
  },
  handler: async (ctx, args) => {
    const stats = await ctx.db.query("userStats").first();
    
    if (stats) {
      await ctx.db.patch(stats._id, {
        totalVideosProcessed: stats.totalVideosProcessed + 1,
        totalProcessingTime: stats.totalProcessingTime + args.processingTime,
        totalCost: stats.totalCost + args.cost,
        lastUpdated: Date.now(),
      });
    } else {
      await ctx.db.insert("userStats", {
        totalVideosProcessed: 1,
        totalProcessingTime: args.processingTime,
        totalCost: args.cost,
        lastUpdated: Date.now(),
      });
    }
  },
});