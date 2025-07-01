import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  processedVideos: defineTable({
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
    createdAt: v.number(),
  }).index("by_video_id", ["videoId"]),
  
  userStats: defineTable({
    totalVideosProcessed: v.number(),
    totalProcessingTime: v.number(),
    totalCost: v.number(),
    lastUpdated: v.number(),
  }),
});