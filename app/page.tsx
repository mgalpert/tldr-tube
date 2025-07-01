"use client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState, useEffect } from "react";
import PurpleGradientBackground from "@/components/gradient-background";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import MuxVideo from "@mux/mux-video-react";
import { getJobStatus, submitVideo, isolateGuest } from "./actions";
import { WavesBackground } from "@/components/waves-background";
import YouTubeSegmentPlayer from "@/components/yt-player";
import YouTubeConcatenatedPlayer from "@/components/yt-player";
import { LogoIcon } from "./SieveLogo";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useQuery, useMutation } from "convex/react";
import { api } from "@/convex/_generated/api";
import { calculateProcessingCost, formatCost } from "@/lib/costs";
import Link from "next/link";

const pollJobStatus = async (jobId: string): Promise<any[] | undefined> => {
  console.log("Polling job", jobId);

  const poll = async (): Promise<any[] | undefined> => {
    while (true) {
      const data = await getJobStatus(jobId);
      try {
        if (data.status === "finished") {
          console.log("Final job data:", data);
          return data.outputs[0].data;
        } else if (data.status === "error") {
          console.error("Job failed:", data);
          return;
        }

        // Wait 5 seconds before polling again
        await new Promise((resolve) => setTimeout(resolve, 5000));
      } catch (err) {
        console.error("Polling error:", err);
        return;
      }
    }
  };

  return await poll();
};

const fetchVideo = async (
  videoUrl: string,
  mode: string
): Promise<any[] | undefined> => {
  console.log("fetching video...");
  let jobId;
  if (mode === "guest-only") {
    jobId = await isolateGuest(videoUrl);
  } else {
    jobId = await submitVideo(videoUrl, mode);
  }
  if (!jobId) return;
  return await pollJobStatus(jobId);
};

const getYouTubeVideoId = (url: string): string | null => {
  const regex =
    /(?:youtube\.com\/(?:watch\?.*v=|embed\/|v\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
  const match = url.match(regex);
  return match ? match[1] : null;
};

export default function Home() {
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [mode, setMode] = useState<string>("guest-only");
  const [resultSegments, setResultSegments] = useState<any[]>([]);
  const [speakerData, setSpeakerData] = useState<any>(null);
  const [showSpeakerSelect, setShowSpeakerSelect] = useState(false);
  const [excludedSpeakers, setExcludedSpeakers] = useState<string[]>([]);
  const [processingStartTime, setProcessingStartTime] = useState<number>(0);
  const [processingCost, setProcessingCost] = useState<number>(0);

  // Convex hooks
  const saveVideo = useMutation(api.videos.saveProcessedVideo);
  const updateStats = useMutation(api.videos.updateUserStats);
  const cachedVideo = useQuery(api.videos.getProcessedVideo, 
    videoUrl ? { videoId: getYouTubeVideoId(videoUrl) || "" } : "skip"
  );

  // Load saved results from localStorage on mount
  useEffect(() => {
    const savedResults = localStorage.getItem("lastVideoResults");
    if (savedResults) {
      const { url, segments, speakers, excluded } = JSON.parse(savedResults);
      setVideoUrl(url);
      setResultSegments(segments);
      if (speakers) {
        setSpeakerData(speakers);
        setExcludedSpeakers(excluded || []);
      }
    }
  }, []);

  const demoVideos = [
    {
      before: "https://www.youtube.com/embed/Qc_kEyLsXH0",
      after: "CYynvup01VsZiAoqSRhMOaNhJPGjlCn6dvYY02to00vRIc",
      percent: 73,
    },
    {
      before: "https://www.youtube.com/embed/D29swWwYXkI",
      after: "aGS6zfokZjcQ1jrO5KaIZ00XxkHiKXw6fxdlEdudkCRQ",
      percent: 85,
    },
    {
      before: "https://www.youtube.com/embed/nlm6JmqC2QU",
      after: "ARi2gSyfAeqQtvJQ01vUXPWdU1Fgd5JxDZ3lHSYwKDek",
      percent: 72,
    },
  ];

  const filterSegmentsBySpeaker = (speakers: any[], excluded: string[]) => {
    console.log("Filtering segments. Speakers:", speakers);
    console.log("Excluded speakers:", excluded);
    
    const filtered: any[] = [];
    
    for (const speaker of speakers) {
      console.log(`Checking speaker ${speaker.id}, excluded: ${excluded.includes(speaker.id)}`);
      if (!excluded.includes(speaker.id)) {
        console.log(`Including ${speaker.segments.length} segments from speaker ${speaker.id}`);
        for (const segment of speaker.segments) {
          filtered.push({
            start: Math.max(0, segment.start - 0.1),
            end: segment.end + 0.1
          });
        }
      } else {
        console.log(`Excluding speaker ${speaker.id}`);
      }
    }
    
    console.log(`Total filtered segments before merge: ${filtered.length}`);
    
    // Sort and merge overlapping segments
    filtered.sort((a, b) => a.start - b.start);
    const merged = [];
    for (const segment of filtered) {
      if (merged.length > 0 && segment.start - merged[merged.length - 1].end < 1.0) {
        merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, segment.end);
      } else {
        merged.push(segment);
      }
    }
    
    console.log(`Final merged segments: ${merged.length}`);
    return merged;
  };

  const processVideo = async () => {
    const videoId = getYouTubeVideoId(videoUrl);
    if (!videoId) {
      alert("Invalid YouTube URL");
      return;
    }

    // Check if we have cached results
    if (cachedVideo) {
      console.log("Using cached video data");
      setSpeakerData(cachedVideo.speakers);
      setShowSpeakerSelect(true);
      setExcludedSpeakers([cachedVideo.identifiedHost]);
      
      // Calculate segments from cached data
      const segments = filterSegmentsBySpeaker(cachedVideo.speakers, [cachedVideo.identifiedHost]);
      setResultSegments(segments);
      
      // Save to localStorage
      localStorage.setItem("lastVideoResults", JSON.stringify({
        url: videoUrl,
        segments: segments,
        speakers: cachedVideo.speakers,
        excluded: [cachedVideo.identifiedHost]
      }));
      
      return;
    }

    // Process new video
    setLoading(true);
    setProcessingStartTime(Date.now());
    
    const result = await fetchVideo(videoUrl, mode);
    if (result) {
      console.log("result", result);
      
      const processingTime = (Date.now() - processingStartTime) / 1000; // in seconds
      
      // Check if result is an object with speakers (new format) or just segments (old format)
      if (mode === "guest-only" && result && typeof result === 'object' && result.speakers) {
        // Calculate cost based on video duration
        const totalDuration = result.speakers.reduce((sum: number, speaker: any) => 
          sum + speaker.totalTime, 0
        );
        const cost = calculateProcessingCost(totalDuration);
        setProcessingCost(cost.total);
        
        // Save to Convex
        await saveVideo({
          videoId,
          videoUrl,
          title: undefined, // Could extract from YouTube API
          speakers: result.speakers,
          identifiedHost: result.identifiedHost,
          processingTime,
          processingCost: cost.total,
        });
        
        // Update user stats
        await updateStats({
          processingTime,
          cost: cost.total,
        });
        
        // For guest-only mode with new format, show speaker selection
        setSpeakerData(result.speakers);
        setShowSpeakerSelect(true);
        setExcludedSpeakers([result.identifiedHost]);
        
        // Use the pre-filtered segments for now
        setResultSegments(result.segments);
        
        // Save to localStorage
        localStorage.setItem("lastVideoResults", JSON.stringify({
          url: videoUrl,
          segments: result.segments,
          speakers: result.speakers,
          excluded: [result.identifiedHost]
        }));
      } else if (Array.isArray(result)) {
        // Old format - just segments array
        setResultSegments(result);
        
        // Save to localStorage
        localStorage.setItem("lastVideoResults", JSON.stringify({
          url: videoUrl,
          segments: result
        }));
      } else {
        // For other modes, just use segments directly
        setResultSegments(result);
        
        // Save to localStorage
        localStorage.setItem("lastVideoResults", JSON.stringify({
          url: videoUrl,
          segments: result
        }));
      }
    }
    setLoading(false);
  };

  return (
    <main className="flex flex-col items-center justify-center gap-4 px-4">
      <WavesBackground />
      
      {/* Header with History Link */}
      <div className="absolute top-4 right-4">
        <Link 
          href="/history"
          className="bg-white/90 backdrop-blur-md border rounded-full px-4 py-2 text-sm hover:bg-white"
        >
          View History
        </Link>
      </div>
      
      {resultSegments.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-4 h-[25rem] w-full px-4">
          {!loading && (
            <>
              <h1 className="font-bold text-5xl">
                Lex <b className="bg-primary p-2 text-white">minus</b> Lex
              </h1>
              <span>Remove podcast hosts and keep only the guests.</span>
              <div className="flex items-center gap-2">
                <Input
                  placeholder="Youtube Video Url"
                  value={videoUrl}
                  onChange={(e) => setVideoUrl(e.target.value)}
                  className="md:w-[25rem] bg-background"
                  disabled={loading}
                />
                <Select value={mode} onValueChange={(value) => setMode(value)}>
                  <SelectTrigger className="w-[8rem]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="guest-only">Guest Only</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  className="cursor-pointer"
                  onClick={() => processVideo()}
                  disabled={loading}
                >
                  Generate
                </Button>
              </div>
            </>
          )}

          {loading && (
            <div className="flex flex-col gap-2 md:h-full w-full items-center justify-center">
              <span className="font-bold text-xl text-primary">
                {mode === "guest-only" ? "Isolating guest speaker..." : "TLDRing your video..."}
              </span>
              <div className="flex flex-col md:flex-row gap-2 w-full items-center justify-center">
                <iframe
                  className="w-2/3 md:w-1/3 xl:w-1/4 aspect-video"
                  src={`https://www.youtube.com/embed/${getYouTubeVideoId(
                    videoUrl
                  )}`}
                ></iframe>
                <Skeleton className="w-2/3 md:w-1/3 xl:w-1/4 aspect-video border border-primary flex flex-col items-center justify-center">
                  <Spinner />
                  <span className="text-sm text-muted-foreground">
                    This may take 2-3 minutes...
                  </span>
                </Skeleton>
              </div>
            </div>
          )}
        </div>
      )}

      {resultSegments.length > 0 && (
        <>
          {speakerData && showSpeakerSelect && (
            <div className="bg-white/90 backdrop-blur-md border rounded-lg p-4 w-full md:w-2/3 mb-4">
              {cachedVideo && (
                <div className="bg-green-100 border border-green-300 rounded p-2 mb-4">
                  <p className="text-sm text-green-800">
                    ✓ Using cached results - saved {formatCost(cachedVideo.processingCost)}!
                  </p>
                </div>
              )}
              {processingCost > 0 && !cachedVideo && (
                <div className="bg-blue-100 border border-blue-300 rounded p-2 mb-4">
                  <p className="text-sm text-blue-800">
                    Processing cost: {formatCost(processingCost)}
                  </p>
                </div>
              )}
              <h3 className="font-bold text-lg mb-2">Speaker Selection</h3>
              <p className="text-sm text-gray-600 mb-4">
                Uncheck speakers to exclude them from playback:
              </p>
              <div className="space-y-2">
                {speakerData.map((speaker: any) => (
                  <label key={speaker.id} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={!excludedSpeakers.includes(speaker.id.toString())}
                      onChange={(e) => {
                        const speakerId = speaker.id.toString();
                        const newExcluded = e.target.checked
                          ? excludedSpeakers.filter(id => id !== speakerId)
                          : [...excludedSpeakers, speakerId];
                        setExcludedSpeakers(newExcluded);
                        
                        // Update segments based on new selection
                        const newSegments = filterSegmentsBySpeaker(speakerData, newExcluded);
                        console.log("Speaker ID:", speakerId, "Type:", typeof speakerId);
                        console.log("New excluded speakers:", newExcluded);
                        console.log("New segments:", newSegments);
                        setResultSegments(newSegments);
                        
                        // Update localStorage
                        const savedData = localStorage.getItem("lastVideoResults");
                        if (savedData) {
                          const parsed = JSON.parse(savedData);
                          localStorage.setItem("lastVideoResults", JSON.stringify({
                            ...parsed,
                            segments: newSegments,
                            excluded: newExcluded
                          }));
                        }
                      }}
                      className="w-4 h-4"
                    />
                    <span className="flex-1">
                      <strong>{speaker.id}</strong> - 
                      {Math.round(speaker.totalTime)}s total, 
                      {speaker.segmentCount} segments
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}
          <YouTubeConcatenatedPlayer
            videoId={getYouTubeVideoId(videoUrl)!}
            segments={resultSegments}
            speakerData={speakerData}
            excludedSpeakers={excludedSpeakers}
            clickFunction={() => {
              setResultSegments([]);
              setSpeakerData(null);
              setShowSpeakerSelect(false);
              setExcludedSpeakers([]);
              localStorage.removeItem("lastVideoResults");
            }}
          />
        </>
      )}

      {/* {resultSegments.length === 0 && (
        <div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 rounded
       gap-4 mb-[7rem] w-full md:w-3/4 px-4 bg-[#ffffff66] backdrop-blur-md border p-3"
        >
          {demoVideos.map((video) => (
            <div
              className="flex flex-col items-center gap-2"
              key={video.before}
            >
              <span>Original:</span>
              <iframe
                className="w-full aspect-video"
                src={video.before}
              ></iframe>
              <span className="font-bold text-primary">
                {video.percent}
                {"% Reduction!"}
              </span>
              <MuxVideo
                playbackId={video.after}
                className="w-full aspect-video"
                controls
                autoPlay={false}
              />
            </div>
          ))}
        </div>
      )} */}
      
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
          {" • "}
          inspired by{" "}
          <a
            href="https://garfieldminusgarfield.net/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            garfield minus garfield
          </a>
          {" • "}
          forked{" "}
          <a
            href="https://x.com/awdii_"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            @awdii_
          </a>
          's{" "}
          <a
            href="https://github.com/sieve-data/tldr-tube"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            repo
          </a>
          {" • "}
          code is{" "}
          <a
            href="https://github.com/mgalpert/tldr-tube"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            open-sourced
          </a>
        </p>
      </footer>
    </main>
  );
}
