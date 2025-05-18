"use client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState } from "react";
import PurpleGradientBackground from "@/components/gradient-background";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import MuxVideo from "@mux/mux-video-react";
import { getJobStatus, submitVideo } from "./actions";
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
  const jobId = await submitVideo(videoUrl, mode);
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
  const [mode, setMode] = useState<string>("fast");
  const [resultSegments, setResultSegments] = useState<any[]>([]);

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

  const processVideo = async () => {
    setLoading(true);
    const result = await fetchVideo(videoUrl, mode);
    if (result) {
      // setResultVideo(result);
      setResultSegments(result);
      console.log("result", result);
    }
    setLoading(false);
  };

  return (
    <main className="flex flex-col items-center justify-center gap-4 px-4">
      <WavesBackground />
      <a
        className="flex p-2 px-4 items-center gap-3 absolute top-2 right-2 text-sm rounded 
       bg-[#Affffff66] backdrop-blur-md border rounded-full hover:bg-muted cursor-pointer"
        href={"https://www.sievedata.com/"}
      >
        Powered by
        <LogoIcon />
      </a>
      {resultSegments.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-4 h-[25rem] w-full px-4">
          {!loading && (
            <>
              <h1 className="font-bold text-5xl">
                <b className="bg-primary p-2 text-white">TLDR</b> Tube
              </h1>
              <span>Make any youtube video ADHD friendly.</span>
              <div className="flex items-center gap-2">
                <Input
                  placeholder="Youtube Video Url"
                  value={videoUrl}
                  onChange={(e) => setVideoUrl(e.target.value)}
                  className="md:w-[25rem] bg-background"
                  disabled={loading}
                />
                <Select value={mode} onValueChange={(value) => setMode(value)}>
                  <SelectTrigger className="w-[6rem]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fast">Fast</SelectItem>
                    <SelectItem value="quality">Quality</SelectItem>
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
                TLDRing your video...
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
        <YouTubeConcatenatedPlayer
          videoId={getYouTubeVideoId(videoUrl)!}
          segments={resultSegments}
          clickFunction={() => setResultSegments([])}
        />
      )}

      {resultSegments.length === 0 && (
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
      )}
    </main>
  );
}
