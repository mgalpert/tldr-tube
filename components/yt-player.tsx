import { useEffect, useRef, useState, useCallback } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Slider } from "./ui/slider";

export type Segment = { start: number; end: number }; // seconds

interface Props {
  videoId: string;
  segments: Segment[];
  clickFunction: () => void;
  height?: number;
  width?: number;
}

declare global {
  interface Window {
    YT: any;
    onYouTubeIframeAPIReady: () => void;
  }
}

export default function YouTubeConcatenatedPlayer({
  videoId,
  segments,
  clickFunction,
  height = 720,
  width = 1280,
}: Props) {
  /* ---------- pre-compute helpers ---------- */
  const segLengths = segments.map((s) => s.end - s.start);
  const totalDuration = segLengths.reduce((a, b) => a + b, 0);

  const cumulative = segments.reduce<number[]>((acc, s, i) => {
    acc[i] =
      (acc[i - 1] ?? 0) +
      (i === 0 ? 0 : segments[i - 1].end - segments[i - 1].start);
    return acc;
  }, []);

  const realToVirtual = (real: number) => {
    let idx = segments.findIndex((s) => real >= s.start && real < s.end);
    if (idx === -1) {
      if (segments.length > 0 && real < segments[0].start) {
        idx = 0;
      } else {
        idx = segments.length - 1;
      }
    }
    return cumulative[idx] + (real - segments[idx].start);
  };

  const virtualToReal = (virtual: number) => {
    let idx = segments.findIndex(
      (_, i) =>
        virtual >= cumulative[i] && virtual < cumulative[i] + segLengths[i]
    );
    if (idx === -1) {
      if (segments.length > 0 && virtual < cumulative[0]) {
        idx = 0;
      } else {
        idx = segments.length - 1;
      }
    }
    return segments[idx].start + (virtual - cumulative[idx]);
  };

  /* ---------- refs & state ---------- */
  const playerRef = useRef<any>(null);
  const rafId = useRef<number | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [virtualTime, setVirtualTime] = useState(0);
  const [originalDuration, setOriginalDuration] = useState<number | null>(null);
  const [playbackRate, setPlaybackRate] = useState<1 | 2>(1); // NEW ▶ default 2x

  const reductionPercent = originalDuration
    ? 100 * (1 - totalDuration / originalDuration)
    : null;

  /* ---------- helper: cycle playback rate ---------- */
  const cycleRate = useCallback(() => {
    const next: 1 | 2 | 4 = playbackRate === 2 ? 1 : 2;
    setPlaybackRate(next);
    if (playerRef.current?.setPlaybackRate) {
      playerRef.current.setPlaybackRate(next);
    }
  }, [playbackRate]);

  /* ---------- player bootstrap ---------- */
  useEffect(() => {
    const loadIframeAPI = () => {
      const tag = document.createElement("script");
      tag.src = "https://www.youtube.com/iframe_api";
      const firstScriptTag = document.getElementsByTagName("script")[0];
      if (firstScriptTag && firstScriptTag.parentNode) {
        firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
      } else {
        document.head.appendChild(tag);
      }
    };

    window.onYouTubeIframeAPIReady = () => {
      if (playerRef.current) return; // already initialized
      playerRef.current = new window.YT.Player("yt-cc-player", {
        width: "100%",
        height: "100%",
        videoId,
        playerVars: {
          controls: 0,
          modestbranding: 1,
          rel: 0,
          iv_load_policy: 3,
          autoplay: 0,
          disablekb: 1,
        },
        events: {
          onReady: (event: any) => {
            setIsReady(true);
            const fullDuration = event.target.getDuration?.();
            if (typeof fullDuration === "number" && !isNaN(fullDuration)) {
              setOriginalDuration(fullDuration);
            }
            // ⏩ set initial playback rate
            if (event.target.setPlaybackRate) {
              // YouTube supports up to 2× officially; attempting 4× may silently fail.
              event.target.setPlaybackRate(playbackRate);
            }
            if (segments.length > 0) {
              seekVirtual(0);
            }
          },
          onStateChange: (event: any) => {
            if (event.data === window.YT.PlayerState.PLAYING) {
              if (!playing) {
                setPlaying(true);
                if (!rafId.current) rafId.current = requestAnimationFrame(tick);
              }
            } else if (
              event.data === window.YT.PlayerState.PAUSED ||
              event.data === window.YT.PlayerState.ENDED
            ) {
              if (playing) {
                setPlaying(false);
                stopRaf();
              }
              if (
                event.data === window.YT.PlayerState.ENDED &&
                segments.length > 0
              ) {
                const currentSegIdx = segments.findIndex(
                  (_, i) =>
                    virtualTime >= cumulative[i] &&
                    virtualTime < cumulative[i] + segLengths[i]
                );
                if (currentSegIdx === segments.length - 1) {
                  setVirtualTime(totalDuration);
                }
              }
            }
          },
        },
      });
    };

    if (!window.YT || !window.YT.Player) {
      loadIframeAPI();
    } else if (!playerRef.current) {
      window.onYouTubeIframeAPIReady();
    }

    return () => {
      // cleanup
    };
  }, [videoId, height, width, segments, playbackRate]);

  /* ---------- playback helpers ---------- */
  const stopRaf = () => {
    if (rafId.current) cancelAnimationFrame(rafId.current);
    rafId.current = null;
  };

  const tick = useCallback(() => {
    if (!playerRef.current?.getCurrentTime) {
      stopRaf();
      return;
    }
    const realNow = playerRef.current.getCurrentTime();
    const virtNow = realToVirtual(realNow);

    let currentSegIdx = segments.findIndex(
      (_, i) =>
        virtNow >= cumulative[i] && virtNow < cumulative[i] + segLengths[i]
    );
    if (currentSegIdx === -1 && virtNow >= totalDuration && totalDuration > 0) {
      currentSegIdx = segments.length - 1;
    } else if (currentSegIdx === -1 && segments.length > 0) {
      currentSegIdx = 0;
    }

    if (currentSegIdx !== -1 && segments[currentSegIdx]) {
      const currentSegment = segments[currentSegIdx];
      const segEndVirtual =
        cumulative[currentSegIdx] + segLengths[currentSegIdx];

      if (
        realNow < currentSegment.start - 0.1 ||
        realNow >= currentSegment.end - 0.1 ||
        virtNow >= segEndVirtual - 0.1
      ) {
        const nextSegIdx = currentSegIdx + 1;
        if (virtNow >= segEndVirtual - 0.1 && nextSegIdx < segments.length) {
          playerRef.current.seekTo(segments[nextSegIdx].start, true);
        } else if (
          virtNow >= totalDuration - 0.1 ||
          realNow >= segments[segments.length - 1].end - 0.1
        ) {
          setPlaying(false);
          stopRaf();
          setVirtualTime(totalDuration);
          playerRef.current.pauseVideo();
          return;
        }
      }
    } else if (segments.length === 0) {
      setPlaying(false);
      stopRaf();
      setVirtualTime(0);
      playerRef.current?.pauseVideo();
      return;
    }

    setVirtualTime(Math.min(virtNow, totalDuration));
    rafId.current = requestAnimationFrame(tick);
  }, [segments, segLengths, cumulative, totalDuration, realToVirtual]);

  /* ---------- control helpers ---------- */
  const handlePlayPause = () => {
    if (!isReady || !playerRef.current) return;
    if (segments.length === 0 && totalDuration === 0) return;
    playing ? pause() : play();
  };

  const play = () => {
    if (!isReady || !playerRef.current) return;
    if (segments.length === 0) return;

    if (virtualTime >= totalDuration - 0.05 && totalDuration > 0) {
      seekVirtual(0);
    } else if (virtualTime < 0.1) {
      const firstSegmentRealStart = segments[0].start;
      if (
        playerRef.current.getCurrentTime &&
        Math.abs(playerRef.current.getCurrentTime() - firstSegmentRealStart) >
          0.2
      ) {
        playerRef.current.seekTo(firstSegmentRealStart, true);
      }
    }

    playerRef.current.playVideo();
    setPlaying(true);
    stopRaf();
    rafId.current = requestAnimationFrame(tick);
  };

  const pause = () => {
    if (!isReady || !playerRef.current) return;
    playerRef.current.pauseVideo();
    setPlaying(false);
    stopRaf();
  };

  const seekVirtual = (virtual: number) => {
    if (!isReady || !playerRef.current) return;
    const clampedVirtual = Math.max(0, Math.min(virtual, totalDuration));
    const real = virtualToReal(clampedVirtual);
    playerRef.current.seekTo(real, true);
    setVirtualTime(clampedVirtual);
    if (!playing) {
      stopRaf();
    } else {
      stopRaf();
      rafId.current = requestAnimationFrame(tick);
    }
  };

  /* ---------- cleanup ---------- */
  useEffect(() => {
    return () => {
      stopRaf();
    };
  }, []);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  /* ---------- UI ---------- */
  return (
    <div className="flex flex-col items-center justify-center gap-4 h-[100dvh] w-[100dvw] bg-black/20 z-10">
      <span className="font-black text-primary text-4xl">
        {reductionPercent?.toFixed(0)}% Reduction!
      </span>

      {/* ‣ Responsive wrapper: full width on sm, 3/4 on md+, fixed 16:9 */}
      <div className="relative w-full md:w-3/4 aspect-video">
        {/* Player fills the wrapper */}
        <div id="yt-cc-player" className="absolute inset-0" />
        {/* Click-through overlay */}
        <div
          className="absolute inset-0 z-10"
          onClick={handlePlayPause}
          aria-label={playing ? "Pause video" : "Play video"}
        />
      </div>

      {/* ‣ Controls */}
      <div className="flex items-center gap-2 w-full md:w-3/4">
        <Button
          onClick={handlePlayPause}
          className="rounded px-3 py-1 border w-[3rem]"
          disabled={!isReady || segments.length === 0}
        >
          {playing ? "Pause" : "Play"}
        </Button>

        <Button
          onClick={cycleRate}
          className="rounded px-3 py-1 border w-[3rem]"
          disabled={!isReady || segments.length === 0}
          title="Toggle speed"
        >
          {playbackRate}x
        </Button>

        <Slider
          min={0}
          max={totalDuration}
          step={0.1}
          value={[virtualTime]}
          onValueChange={(value) => seekVirtual(value[0])}
          className="flex-1 text-primary"
          disabled={!isReady || segments.length === 0}
        />

        <span className="tabular-nums text-right text-sm">
          {formatTime(virtualTime)} / {formatTime(totalDuration)}
        </span>
      </div>

      <Button className="cursor-pointer" onClick={clickFunction}>
        Try Another!
      </Button>
    </div>
  );
}
