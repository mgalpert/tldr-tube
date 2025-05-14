"use client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState } from "react";
import PurpleGradientBackground from "@/components/gradient-background";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import MuxVideo from "@mux/mux-video-react";
import { getJobStatus, submitVideo } from "./actions";

export const pollJobStatus = async (
  jobId: string
): Promise<string | undefined> => {
  console.log("Polling job", jobId);

  const poll = async (): Promise<string | undefined> => {
    while (true) {
      const data = await getJobStatus(jobId);
      try {
        if (data.status === "finished") {
          console.log("Final job data:", data);
          return data.outputs[0].data.url;
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

const fetchVideo = async (videoUrl: string): Promise<string | undefined> => {
  console.log("fetching video");
  const jobId = await submitVideo(videoUrl);
  if (!jobId) return;
  return await pollJobStatus(jobId);
};

const convertVideoToEmbed = (videoUrl: string) => {
  // https://www.youtube.com/watch?v=8QyygfIloMc
  const vidID = videoUrl.split("=")[1];
  return `https://www.youtube.com/embed/${vidID}`;
};

export default function Home() {
  const [videoUrl, setVideoUrl] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [resultVideo, setResultVideo] = useState<string>("");
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
    const result = await fetchVideo(videoUrl);
    if (result) {
      setResultVideo(result);
      console.log("result", result);
    }
    setLoading(false);
  };

  return (
    <main className="flex flex-col items-center justify-center gap-4">
      {/* <WaveLinesBackground /> */}
      <PurpleGradientBackground />
      <div className="flex flex-col items-center justify-center gap-4 h-[25rem] w-full">
        {!loading && !resultVideo && (
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
                className="w-[25rem] bg-background"
                disabled={loading}
              />
              <Button onClick={() => processVideo()} disabled={loading}>
                Generate
              </Button>
            </div>
          </>
        )}
        {resultVideo && (
          <video
            className="h-3/4 aspect-video border border-primary"
            src={resultVideo}
            controls
          />
        )}
        {loading && (
          <div className="flex flex-row gap-2 h-full w-full items-center justify-center">
            <iframe
              className="w-1/3 aspect-video"
              src={convertVideoToEmbed(videoUrl)}
            ></iframe>
            <Skeleton className="w-1/3 aspect-video border border-primary flex items-center justify-center">
              <Spinner />
            </Skeleton>
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-4 pb-[20rem] w-3/4">
        {demoVideos.map((video) => (
          <div className="flex flex-col items-center gap-2" key={video.before}>
            <span>Original:</span>
            <iframe className="w-full aspect-video" src={video.before}></iframe>
            <span className="font-bold text-primary">
              {video.percent}
              {"% Reduction!"}
            </span>
            <MuxVideo
              playbackId={video.after}
              className="w-full aspect-video"
              controls
            />
          </div>
        ))}
      </div>
    </main>
  );
}
