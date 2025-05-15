// YouTubeConcatenatedPlayer.tsx
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
  height = 324,
  width = 576,
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
      // If real time is before the first segment or after the last
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
      // If virtual time is outside all segments, clamp to nearest
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
  const reductionPercent = originalDuration
    ? 100 * (1 - totalDuration / originalDuration)
    : null;

  /* ---------- player bootstrap ---------- */
  useEffect(() => {
    const loadIframeAPI = () => {
      const tag = document.createElement("script");
      tag.src = "https://www.youtube.com/iframe_api";
      const firstScriptTag = document.getElementsByTagName("script")[0];
      if (firstScriptTag && firstScriptTag.parentNode) {
        firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
      } else {
        document.head.appendChild(tag); // Fallback if no script tags
      }
    };

    window.onYouTubeIframeAPIReady = () => {
      if (playerRef.current) {
        // Avoid re-initializing if already exists
        return;
      }
      playerRef.current = new window.YT.Player("yt-cc-player", {
        height: String(height), // API expects string
        width: String(width), // API expects string
        videoId,
        playerVars: {
          controls: 0,
          modestbranding: 1,
          rel: 0,
          iv_load_policy: 3, // disable annotations
          autoplay: 0, // ensure no autoplay on load
          disablekb: 1, // disable keyboard controls for the iframe
        },
        events: {
          onReady: (event: any) => {
            setIsReady(true);
            // Ensure player is muted initially if desired, or for autoplay policies
            // playerRef.current.mute();
            const fullDuration = event.target.getDuration?.();
            if (typeof fullDuration === "number" && !isNaN(fullDuration)) {
              setOriginalDuration(fullDuration);
            }
            if (segments.length > 0) {
              seekVirtual(0);
            }
          },
          // It's good practice to also listen to onStateChange to manage play/pause state
          // if the user somehow interacts with the player (e.g., via keyboard if not disabled)
          onStateChange: (event: any) => {
            if (event.data === window.YT.PlayerState.PLAYING) {
              if (!playing) {
                // Sync state if changed externally
                setPlaying(true);
                if (!rafId.current) rafId.current = requestAnimationFrame(tick);
              }
            } else if (
              event.data === window.YT.PlayerState.PAUSED ||
              event.data === window.YT.PlayerState.ENDED
            ) {
              if (playing) {
                // Sync state
                setPlaying(false);
                stopRaf();
              }
              if (
                event.data === window.YT.PlayerState.ENDED &&
                segments.length > 0
              ) {
                // If the underlying video ends, and it's the last segment, treat as virtual end
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
    } else {
      // If API is already loaded, and player not initialized, initialize it
      if (!playerRef.current) {
        window.onYouTubeIframeAPIReady();
      }
    }

    return () => {
      // Clean up the player instance if the component unmounts
      // and the iframe API is loaded.
      if (
        playerRef.current &&
        typeof playerRef.current.destroy === "function"
      ) {
        // playerRef.current.destroy(); // This can cause issues with HMR
        // playerRef.current = null;
      }
      // It's usually better not to remove onYouTubeIframeAPIReady globally
      // unless you are sure no other component might need it.
      // For HMR, it can be tricky.
    };
  }, [videoId, height, width, segments]); // Added segments to re-init if segments change fundamentally

  /* ---------- playback helpers ---------- */
  const stopRaf = () => {
    if (rafId.current) cancelAnimationFrame(rafId.current);
    rafId.current = null;
  };

  const tick = useCallback(() => {
    if (!playerRef.current || !playerRef.current.getCurrentTime) {
      stopRaf();
      return;
    }
    const realNow = playerRef.current.getCurrentTime();
    const virtNow = realToVirtual(realNow);

    // Find current segment based on virtual time
    let currentSegIdx = segments.findIndex(
      (_, i) =>
        virtNow >= cumulative[i] && virtNow < cumulative[i] + segLengths[i]
    );
    if (currentSegIdx === -1 && virtNow >= totalDuration && totalDuration > 0) {
      // Handle end of all segments
      currentSegIdx = segments.length - 1;
    } else if (currentSegIdx === -1 && segments.length > 0) {
      // Default to first if not found (e.g. before start)
      currentSegIdx = 0;
    }

    if (currentSegIdx !== -1 && segments[currentSegIdx]) {
      const currentSegment = segments[currentSegIdx];
      const segEndVirtual =
        cumulative[currentSegIdx] + segLengths[currentSegIdx];

      // If real time is outside the current segment's bounds (e.g. due to YouTube's own buffering skips)
      // or if we are very close to the end of a segment
      if (
        realNow < currentSegment.start - 0.1 ||
        realNow >= currentSegment.end - 0.1 ||
        virtNow >= segEndVirtual - 0.1
      ) {
        const nextSegIdx = currentSegIdx + 1;
        if (virtNow >= segEndVirtual - 0.1 && nextSegIdx < segments.length) {
          // Move to next segment
          const targetReal = segments[nextSegIdx].start;
          playerRef.current.seekTo(targetReal, true);
          // setVirtualTime might be slightly off due to seekTo, tick will correct
        } else if (
          virtNow >= totalDuration - 0.1 ||
          realNow >= segments[segments.length - 1].end - 0.1
        ) {
          // Finished all segments or reached end of last segment
          setPlaying(false);
          stopRaf();
          setVirtualTime(totalDuration); // Ensure virtual time is exactly at the end
          playerRef.current.pauseVideo(); // Explicitly pause
          return;
        }
      }
    } else if (segments.length === 0) {
      // No segments to play
      setPlaying(false);
      stopRaf();
      setVirtualTime(0);
      if (playerRef.current?.pauseVideo) playerRef.current.pauseVideo();
      return;
    }

    setVirtualTime(Math.min(virtNow, totalDuration)); // Clamp virtual time
    rafId.current = requestAnimationFrame(tick);
  }, [segments, segLengths, cumulative, totalDuration, realToVirtual]); // Removed virtualTime from deps

  // play, pause, handlePlayPause functions with modifications

  const handlePlayPause = () => {
    if (!isReady || !playerRef.current) return;
    // If there are no segments, and the button somehow became enabled, do nothing.
    if (segments.length === 0 && totalDuration === 0) {
      console.warn("Play/Pause clicked but no segments are defined.");
      return;
    }

    if (playing) {
      pause();
    } else {
      play();
    }
  };

  const play = () => {
    if (!isReady || !playerRef.current) return;
    if (segments.length === 0) {
      console.warn("YouTubeConcatenatedPlayer: Play called without segments.");
      return;
    }

    // Case 1: Restarting from the end of the concatenated video
    if (virtualTime >= totalDuration - 0.05 && totalDuration > 0) {
      seekVirtual(0); // This seeks to virtual 0, which maps to segments[0].start
    } else if (virtualTime < 0.1) {
      // Check if virtualTime is at or near the beginning
      const firstSegmentRealStart = segments[0].start;
      if (
        playerRef.current.getCurrentTime &&
        Math.abs(playerRef.current.getCurrentTime() - firstSegmentRealStart) >
          0.2
      ) {
        playerRef.current.seekTo(firstSegmentRealStart, true);
      }
    }

    // If execution reaches here, player is positioned (or was already positioned) correctly.
    playerRef.current.playVideo();
    setPlaying(true);
    stopRaf(); // Clear any existing RAF
    rafId.current = requestAnimationFrame(tick); // Start new RAF for time updates
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
    // If paused and seeking, keep it paused. If playing, seeking should not stop it.
    // However, a seek often triggers a buffer state, then play.
    // The onStateChange handler will manage the playing state.
    // If not playing, ensure RAF is stopped after seek.
    if (!playing) {
      stopRaf();
    } else {
      // If it was playing, restart RAF to ensure UI updates and segment logic continues
      stopRaf();
      rafId.current = requestAnimationFrame(tick);
    }
  };

  /* ---------- cleanup ---------- */
  useEffect(() => {
    return () => {
      stopRaf();
      // Optional: destroy player on unmount. Be careful with HMR.
      // if (playerRef.current && typeof playerRef.current.destroy === 'function') {
      //   playerRef.current.destroy();
      //   playerRef.current = null;
      // }
    };
  }, []);

  function formatTime(seconds: number) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }

  /* ---------- UI ---------- */
  return (
    <div className="flex h-full items-center justify-center gap-10">
      <div className="inline-flex flex-col items-center gap-2">
        <div
          style={{
            position: "relative",
            width: `${width}px`,
            height: `${height}px`,
          }}
        >
          <div id="yt-cc-player" />
          {/* Transparent overlay to prevent clicks on iframe from playing/pausing */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              height: "100%",
              zIndex: 1, // Ensure it's above the iframe
              // backgroundColor: "rgba(255,0,0,0.1)", // For debugging visibility
            }}
            onClick={handlePlayPause} // Make overlay trigger your custom controls
            onDoubleClick={() => {}}
            aria-label={playing ? "Pause video" : "Play video"}
          />
        </div>
        <div
          className="flex items-center gap-2 w-full"
          style={{ maxWidth: `${width}px` }}
        >
          <Button
            onClick={handlePlayPause}
            className="rounded px-3 py-1 border w-[3rem]"
            disabled={!isReady || segments.length === 0}
          >
            {playing ? "Pause" : "Play"}
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
      </div>
      <div className="flex flex-col h-full items-center justify-center gap-4">
        <span className="font-black text-primary text-4xl">
          {reductionPercent?.toFixed(0)}% Reduction!
        </span>
        <Button className="cursor-pointer" onClick={() => clickFunction()}>
          Try Another!
        </Button>
      </div>
    </div>
  );
}
