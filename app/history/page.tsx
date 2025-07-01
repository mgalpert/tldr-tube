"use client";

import { useQuery } from "convex/react";
import { api } from "@/convex/_generated/api";
import Link from "next/link";
import { formatCost, formatDuration } from "@/lib/costs";
import { WavesBackground } from "@/components/waves-background";

export default function HistoryPage() {
  const videos = useQuery(api.videos.getAllProcessedVideos);
  const stats = useQuery(api.videos.getUserStats);

  return (
    <main className="flex flex-col items-center justify-center gap-4 px-4 min-h-screen">
      <WavesBackground />
      
      <div className="w-full max-w-6xl">
        <div className="flex justify-between items-center mb-8">
          <h1 className="font-bold text-4xl">
            Processing History
          </h1>
          <Link 
            href="/"
            className="bg-primary text-white px-4 py-2 rounded hover:opacity-90"
          >
            Back to App
          </Link>
        </div>

        {/* Stats Summary */}
        {stats && (
          <div className="bg-white/90 backdrop-blur-md border rounded-lg p-6 mb-6">
            <h2 className="font-bold text-xl mb-4">Total Statistics</h2>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-sm text-gray-600">Videos Processed</p>
                <p className="text-2xl font-bold">{stats.totalVideosProcessed}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Total Processing Time</p>
                <p className="text-2xl font-bold">{formatDuration(stats.totalProcessingTime)}</p>
              </div>
              <div>
                <p className="text-sm text-gray-600">Total Cost</p>
                <p className="text-2xl font-bold text-green-600">{formatCost(stats.totalCost)}</p>
              </div>
            </div>
          </div>
        )}

        {/* Videos List */}
        <div className="bg-white/90 backdrop-blur-md border rounded-lg p-6">
          <h2 className="font-bold text-xl mb-4">Processed Videos</h2>
          
          {!videos ? (
            <p className="text-gray-500">Loading...</p>
          ) : videos.length === 0 ? (
            <p className="text-gray-500">No videos processed yet.</p>
          ) : (
            <div className="space-y-4">
              {videos.map((video) => (
                <div key={video._id} className="border rounded-lg p-4 hover:bg-gray-50">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <h3 className="font-semibold text-lg">
                        {video.title || "Untitled Video"}
                      </h3>
                      <p className="text-sm text-gray-600 mb-2">
                        {video.videoUrl}
                      </p>
                      <div className="flex gap-4 text-sm">
                        <span>
                          <strong>Speakers:</strong> {video.speakers.length}
                        </span>
                        <span>
                          <strong>Host:</strong> {video.identifiedHost}
                        </span>
                        <span>
                          <strong>Processing:</strong> {formatDuration(video.processingTime)}
                        </span>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-lg font-bold text-green-600">
                        {formatCost(video.processingCost)}
                      </p>
                      <p className="text-xs text-gray-500">
                        {new Date(video.createdAt).toLocaleDateString()}
                      </p>
                      <Link 
                        href={`/?v=${video.videoId}`}
                        className="text-primary text-sm hover:underline mt-2 inline-block"
                      >
                        Load Result →
                      </Link>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <footer className="fixed bottom-0 left-0 right-0 p-4 text-center text-sm text-gray-600">
        <p>
          created by{" "}
          <a
            href="https://x.com/msg"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            @msg
          </a>
          {" & "}
          <a
            href="https://claude.ai"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            Claude
          </a>
        </p>
      </footer>
    </main>
  );
}