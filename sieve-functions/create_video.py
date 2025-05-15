from bisect import bisect, bisect_left, bisect_right
from youtube_transcript_api import YouTubeTranscriptApi
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import List, Literal, Tuple
import time
import sieve
import webvtt
from dotenv import load_dotenv
import openai
import requests
from bs4 import BeautifulSoup


# from google import genai
# from google.genai import types
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed


load_dotenv()

openai_client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://api.openai.com/v1",
)

gemini_client = openai.OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

# client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def download_video(url):
    download_type = "audio"
    resolution = "720p"
    include_audio = True
    start_time = 0
    end_time = -1
    include_metadata = True
    metadata_fields = ["title", "duration"]
    include_subtitles = True
    subtitle_languages = ["en"]
    video_format = "mp4"
    audio_format = "mp3"

    youtube_downloader = sieve.function.get("sieve/youtube-downloader")
    output = youtube_downloader.run(
        url,
        download_type,
        resolution,
        include_audio,
        start_time,
        end_time,
        include_metadata,
        metadata_fields,
        include_subtitles,
        subtitle_languages,
        video_format,
        audio_format,
    )

    for index, output_object in enumerate(output):
        if index == 0:
            title = output_object["title"]
        elif index == 1:
            audio_path = output_object.path
        elif index == 2:
            subtitles_path = output_object["en"].path

    return audio_path, title, subtitles_path


class Subtitle:
    def __init__(self, text: str, start: float, end: float):  # Changed str to float
        self.text = text
        self.start = start
        self.end = end

    # nice-looking representations
    def __str__(self):
        # This formatting will now work correctly as start/end are floats
        return f"{self.start:.3f} – {self.end:.3f} : {self.text}"

    __repr__ = __str__


def load_subtitles(subtitles_path: str) -> List[Subtitle]:
    return [
        Subtitle(
            text=cap.text,
            start=cap.start_in_seconds,  # Use float attribute
            end=cap.end_in_seconds,  # Use float attribute
        )
        for cap in webvtt.read(subtitles_path)
    ]


def safe_json(content: str) -> dict:
    """Return dict even if Gemini gives a bare list or adds ```json fences."""
    # strip ```json fences
    cleaned = re.sub(r"```(?:json)?|```", "", content).strip()

    data = json.loads(cleaned)

    # unwrap `[ {...} ]`
    if isinstance(data, list):
        if len(data) == 1 and isinstance(data[0], dict):
            data = data[0]  # original behaviour
        else:
            # assume the list itself is what you want
            data = {"result": data}

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object or list, got {type(data)}")

    return data


# input_video = sivev


def get_adhd_length(adhd_level: Literal["relaxed", "normal", "hyper"]) -> str:
    if adhd_level == "normal":
        return "1/4th to 1/5th "
    if adhd_level == "hyper":
        return "1/8th to 1/10th "
    if adhd_level == "relaxed":
        return "1/2 to 1/3rd "


SYSTEM_PROMPT = """
You are an AI editor that takes transcripts ofevideos and RUTHLESSLY cuts out any
fluff, and details that aren't relevant to the major points of the video. The goal is
to take a video and make it ADHD friendly, so you should aim for an 75-85% reduction in video length (SO YOU ARE POTENTIALLY CUTTING A LOT).
You are kind of just like a turbo ADHD brain you just wanna get the point of the video and get OUT!
You will be given a chunk of a list of audio segments with their corresponding indices. 
You will be given a chunk at a time not the entire video.
Your goal is to select which indices to include in the video to remove the fluff, while also keeping things coherent.

For example: 

0. "transcript text segment 1..."
1. "transcript text segment 2..."
2. "transcript text segment 3..."


Additionally you will be given a summary of the video which encapsulates the main points that you need 
to include in the video. Also you will be given the title of the video, this is the main thing people 
who are watching the video are trying to figure out.

Please return your response in a JSON array of just the indices of the most important transcript segments
in the video. For example: 

result: {
    [1, 2]
}
"""


def pick_segments(
    subtitles: List[Subtitle],
    summary: str,
    title: str,
    adhd_level: int,
    *,
    chunk_size: int = 100,  # ← slide-window length
    overlap: int = 25,  # ← lines shared with the previous chunk
    max_workers: int = 20,
) -> List[int]:
    """
    Break `subtitles` into overlapping chunks (`chunk_size`, `overlap`)
    and ask Gemini which subtitle indices to keep.

    The result list is deduplicated and sorted.
    """
    if overlap >= chunk_size:
        raise ValueError("`overlap` must be smaller than `chunk_size`")

    step = chunk_size - overlap  # how far we advance the window
    batches: List[List[Tuple[int, Subtitle]]] = []

    # ────────── build overlapping batches ──────────
    start = 0
    while start < len(subtitles):
        end = min(start + chunk_size, len(subtitles))
        batches.append([(i, subtitles[i]) for i in range(start, end)])
        start += step  # slide the window forward

    total_chunks = len(batches)

    # ────────── helpers ──────────
    def _build_prompt(batch: List[Tuple[int, Subtitle]], chunk_num: int) -> str:
        joined = "\n".join(f"{idx}. {sub.text}" for idx, sub in batch)
        return (
            f"This is chunk #{chunk_num} out of {total_chunks} "
            "chunks in the transcript for the length of the video.\n\n"
            "Please reduce this transcript:\n"
            f"{joined}\n"
            "-----------------------------------------\n"
            f"Title:   {title}\n"
            f"Summary: {summary}\n"
        )

    def _call_gemini(batch: List[Tuple[int, Subtitle]], chunk_num: int) -> List[int]:
        prompt = _build_prompt(batch, chunk_num)
        completion = openai_client.chat.completions.create(
            # model="gemini-2.5-flash-preview-04-17",
            model="gpt-4.5-preview",
            # model="gemini-2.5-pro-preview-05-06",
            # reasoning_effort="medium",
            messages=[
                {
                    "role": "user",
                    "content": SYSTEM_PROMPT.replace(
                        "VIDEO_REDUCTION_AMOUNT", get_adhd_length(adhd_level)
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        data = safe_json(completion.choices[0].message.content)["result"]
        print(f"Chunk {chunk_num} result, ", data)
        return data if isinstance(data, list) else data.get("indices", [])

    # ────────── launch requests in parallel ──────────
    chosen: List[int] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, total_chunks)) as pool:
        futures = {
            pool.submit(_call_gemini, batch, i + 1): i
            for i, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            chosen.extend(map(int, future.result()))

    # remove duplicates introduced by the 25-line overlap
    return sorted(set(chosen))


SUMMARY_SYSTEM_PROMPT = """You are an AI summarizer, that takes in a transcript of a Youtube video
                and summarizes the key main points from that video. Your goal is to boil down the main point of 
                the video and write a shorter version that gets straight to the point and gives you the main information
                that you need. You will also be given the title of the video, this is the main thing people 
                who are watching the video are trying to figure out."""


def generate_summary(subtitles: List[Subtitle], title) -> str:
    joined_subs = "\n".join(f"{i + 1}. {obj.text}" for i, obj in enumerate(subtitles))
    completion = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": SUMMARY_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": f"""
                The video is titled: {title}
                Please generate a summary based on this transcript:
                {joined_subs}""",
            },
        ],
    )

    return completion.choices[0].message.content


def detect_silence_midpoints(
    audio_path: str, silence_duration: float = 0.25
) -> List[float]:
    print(audio_path)
    noise_threshold = "20dB"
    mid_start = time.time()
    cmd = [
        "ffmpeg",
        "-i",
        audio_path,
        # "-vn",
        "-af",
        f"silencedetect=noise=-{noise_threshold}:d={silence_duration}",
        "-f",
        "null",
        "-",
    ]

    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
    stderr_output = result.stderr

    # Extract silence start and end times
    silence_starts = [
        float(m.group(1))
        for m in re.finditer(r"silence_start: (\d+\.?\d*)", stderr_output)
    ]
    silence_ends = [
        float(m.group(1))
        for m in re.finditer(r"silence_end: (\d+\.?\d*)", stderr_output)
    ]

    # Compute midpoints
    midpoints = []
    for start, end in zip(silence_starts, silence_ends):
        if end - start >= silence_duration:
            midpoints.append((start + end) / 2)

    print("Detect midpoints time, ", time.time() - mid_start)

    return midpoints


def _segments_from_subs(subtitles, midpoints):
    sorted_midpoints = sorted(float(m) for m in midpoints)

    def prev_cut(t: float) -> float:
        idx = bisect_right(sorted_midpoints, t) - 1
        return sorted_midpoints[idx] if idx >= 0 else 0.0

    def next_cut(t: float) -> float:
        idx = bisect_left(sorted_midpoints, t)
        return sorted_midpoints[idx] if idx < len(sorted_midpoints) else t

    segs = []
    for s in subtitles:
        start = prev_cut(s.start)
        end = next_cut(s.end)
        if start < end:  # avoid zero-length segments
            segs.append((start, end))
    return segs


def merge_subtitles(
    subtitles: List[Subtitle], include_indices: List[int]
) -> List[Subtitle]:
    included = sorted(
        [subtitles[i] for i in sorted(set(include_indices))], key=lambda s: s.start
    )

    if not included:
        return []

    merged = []

    def copy_sub(sub: Subtitle) -> Subtitle:
        return Subtitle(sub.text, sub.start, sub.end)

    current_block = copy_sub(included[0])

    for sub in included[1:]:
        if abs(sub.start - current_block.end) < 0.01:
            current_block.end = sub.end
            current_block.text += " " + sub.text
        else:
            merged.append(current_block)
            current_block = copy_sub(sub)

    merged.append(current_block)
    return merged


def _merge_segments(segs, *, gap=0.04):
    """
    Merge overlapping or back-to-back segments.
    `gap` is the max silence (seconds) to still treat as contiguous.
    """
    if not segs:
        return []

    segs = sorted(segs, key=lambda p: p[0])  # sort by start
    merged = [segs[0]]

    for start, end in segs[1:]:
        last_s, last_e = merged[-1]
        if start <= last_e + gap:  # overlap or tiny gap
            merged[-1] = (last_s, max(last_e, end))  # extend
        else:
            merged.append((start, end))

    return merged


def convert_segments_to_dicts(segments):
    return [{"start": start, "end": end} for start, end in segments]


import subprocess
import os
import tempfile
import re


def get_keyframe_times(video_path):
    """
    Gets keyframe timestamps using the ffprobe command:
    ffprobe -select_streams v -show_entries frame=pict_type,pts_time -of csv=p=0 -skip_frame nokey -i <video_path>
    It parses the CSV output where each line is "pts_time,pict_type".
    Keyframes are identified by pict_type 'I'.
    """
    cmd = [
        "ffprobe",
        "-v",
        "error",  # Suppress verbose output, show only errors
        "-select_streams",
        "v:0",  # Select the first video stream (v or v:0)
        "-show_entries",
        "frame=pict_type,pts_time",  # Get picture type and its PTS time
        "-of",
        "csv=p=0",  # CSV output, no print_section (no "frame:")
        "-skip_frame",
        "nokey",  # Only output lines for keyframes (I-frames)
        "-i",
        video_path,
    ]

    kf_times = []
    print(
        f"Attempting to get keyframes for '{video_path}' with command: {' '.join(cmd)}"
    )
    try:
        # We don't redirect to Iframes.txt here, we capture stdout directly
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
        )
        lines = result.stdout.strip().splitlines()

        if not lines and result.stderr:  # If no stdout but there is stderr, print it
            print(
                f"  Warning: ffprobe produced no stdout. Stderr: {result.stderr.strip()}"
            )

        for line_num, line in enumerate(lines):
            parts = line.strip().split(",")
            # Expected format: "pts_time,pict_type" (sometimes with a trailing comma like "0.007000,I,")
            if len(parts) >= 2:
                pts_time_str = parts[0]
                pict_type_str = parts[1]

                # The -skip_frame nokey should ensure only I-frames are here,
                # but a check doesn't hurt if ffprobe behavior varies.
                # However, the command given explicitly uses -skip_frame nokey,
                # so every line *should* be a keyframe.
                # If we were not using -skip_frame nokey, we would check:
                # if pict_type_str.strip().upper() == 'I':

                try:
                    kf_times.append(float(pts_time_str))
                except ValueError:
                    print(
                        f"  Warning: Could not parse pts_time '{pts_time_str}' from line {line_num+1}: '{line}'"
                    )
            elif (
                line.strip()
            ):  # Non-empty line that doesn't split into at least 2 parts
                print(
                    f"  Warning: Malformed line {line_num+1} in ffprobe output: '{line}'"
                )

        kf_times = sorted(list(set(kf_times)))  # Remove duplicates and sort

        if not kf_times:
            # This can happen if the video truly has no keyframes reported by this command,
            # or if ffprobe had an issue that didn't cause a non-zero exit code.
            print(
                f"Warning: ffprobe command executed for '{video_path}' but parsed no keyframe timestamps "
                "from its output. This could mean the video has no detectable keyframes with this command, "
                "or the output was empty/unexpected."
            )
            if result.stdout:
                print(
                    f"  Raw ffprobe stdout (first 500 chars): '{result.stdout[:500]}'"
                )
            if result.stderr:
                print(
                    f"  Raw ffprobe stderr (first 500 chars): '{result.stderr[:500]}'"
                )
            print(
                "  Defaulting to [0.0] as a keyframe. Lossless cutting accuracy will be poor."
            )
            return [0.0]  # Fallback

        print(
            f"Found {len(kf_times)} keyframes. First few: {kf_times[:10]}, Last few: {kf_times[-5:] if len(kf_times) > 5 else kf_times}"
        )
        return kf_times

    except subprocess.CalledProcessError as e:
        print(
            f"Error: ffprobe command failed while trying to get keyframes for '{video_path}'."
        )
        print(f"  Command: {' '.join(e.cmd)}")
        print(f"  Return code: {e.returncode}")
        if e.stderr:
            print(f"  Stderr: {e.stderr.strip()}")
        if e.stdout:
            print(f"  Stdout (if any before error): {e.stdout.strip()}")
        print(
            "Falling back to assuming [0.0] as the only keyframe due to ffprobe error. "
            "Lossless cutting will likely be inaccurate."
        )
        return [0.0]
    except Exception as e_gen:
        print(f"An unexpected Python error occurred in get_keyframe_times: {e_gen}")
        import traceback

        traceback.print_exc()
        print(
            "Falling back to assuming [0.0] as the only keyframe. Results will be inaccurate."
        )
        return [0.0]


def find_closest_keyframe_before_or_at(target_time, keyframe_times):
    """Finds the largest keyframe time less than or equal to target_time."""
    if (
        not keyframe_times
    ):  # Should ideally not happen if get_keyframe_times has a fallback
        print(
            "Critical Warning: find_closest_keyframe_before_or_at called with empty keyframe_times list."
        )
        return max(0.0, target_time)  # A desperate fallback

    valid_kfs = [kf for kf in keyframe_times if kf <= target_time]

    if not valid_kfs:
        # Target time is before the first actual keyframe in the list (e.g., target_time = 0.5, kf_times = [1.0, 2.0])
        # Or target_time is negative.
        # Returning 0.0 here makes ffmpeg -ss 0.0 ... which will then pick the first actual keyframe.
        # This seems like a reasonable behavior.
        return 0.0
    return max(valid_kfs)


def _concat_lossless(video_path, segments, output_path):
    if not os.path.exists(video_path):
        print(f"Error: Video path '{video_path}' does not exist.")
        return

    print("Fetching keyframe information...")
    keyframe_times = get_keyframe_times(video_path)

    if not keyframe_times or (
        len(keyframe_times) == 1
        and keyframe_times[0] == 0.0
        and max(s[0] for s in segments) > 0
    ):
        # This check indicates get_keyframe_times might have failed to find diverse keyframes
        # and we are likely to cut everything from 0.0 if segments start later.
        print(
            "Warning: Keyframe detection might have been suboptimal. Proceeding with available keyframes."
        )

    temp_files = []
    temp_dir = tempfile.mkdtemp(prefix="ffmpeg_concat_")
    list_file_path = os.path.join(temp_dir, "mylist.txt")

    try:
        print(f"Extracting segments to temporary directory: {temp_dir}")
        for i, (ss, to) in enumerate(segments):
            if ss < 0:
                print(
                    f"Segment {i}: Start time {ss:.3f}s is negative. Adjusting to 0.0s."
                )
                ss = 0.0
            if ss >= to:
                print(
                    f"Skipping invalid segment {i}: start time {ss:.3f}s >= end time {to:.3f}s"
                )
                continue

            actual_ss = find_closest_keyframe_before_or_at(ss, keyframe_times)
            duration = to - actual_ss

            if duration <= 1 / 1000:  # Using a small epsilon for duration check
                print(
                    f"Skipping segment {i}: Adjusted duration ({duration:.3f}s) is too small or negative. "
                    f"Original: [{ss:.3f}s, {to:.3f}s], Adjusted start: {actual_ss:.3f}s"
                )
                continue

            if abs(actual_ss - ss) > 0.01:  # Report if start time shifted noticeably
                print(
                    f"Segment {i}: Original start {ss:.3f}s adjusted to keyframe at {actual_ss:.3f}s."
                )

            base, orig_ext = os.path.splitext(os.path.basename(video_path))
            temp_output_segment = os.path.join(
                temp_dir, f"segment_{i}{orig_ext if orig_ext else '.mp4'}"
            )

            # -ss is an input option (fast seek to keyframe at or before actual_ss)
            # -t is duration from that actual_ss
            cmd_extract = [
                "ffmpeg",
                "-y",
                "-ss",
                str(actual_ss),
                "-i",
                video_path,
                "-t",
                str(duration),
                "-c",
                "copy",
                "-map",
                "0",  # Copy all streams
                "-avoid_negative_ts",
                "make_zero",
                temp_output_segment,
            ]
            print(f"  Executing: {' '.join(cmd_extract)}")
            extract_result = subprocess.run(
                cmd_extract,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if extract_result.returncode != 0:
                print(f"  FFmpeg Error during segment {i} extraction:")
                print(f"    Command: {' '.join(cmd_extract)}")
                print(f"    Stdout: {extract_result.stdout}")
                print(f"    Stderr: {extract_result.stderr}")
                print(f"  Skipping segment {i} due to extraction error.")
                continue

            if (
                os.path.exists(temp_output_segment)
                and os.path.getsize(temp_output_segment) > 100
            ):
                temp_files.append(temp_output_segment)
            else:
                print(
                    f"  Warning: Temp segment {temp_output_segment} for seg {i} not created or is empty."
                )
                print(f"    FFmpeg Stdout: {extract_result.stdout}")
                print(f"    FFmpeg Stderr: {extract_result.stderr}")

        if not temp_files:
            print("No valid segments were extracted to concatenate.")
            return

        with open(list_file_path, "w") as f:
            for temp_file in temp_files:
                f.write(f"file '{os.path.basename(temp_file)}'\n")

        print(f"\nConcatenating {len(temp_files)} segments...")
        cmd_concat = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file_path,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            output_path,
        ]
        print(f"  Executing: {' '.join(cmd_concat)}")
        concat_result = subprocess.run(
            cmd_concat,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if concat_result.returncode != 0:
            print(f"  FFmpeg Error during final concatenation:")
            print(f"    Command: {' '.join(cmd_concat)}")
            print(f"    Stdout: {concat_result.stdout}")
            print(f"    Stderr: {concat_result.stderr}")
            print(
                f"  Concatenation failed. Output file '{output_path}' may be incomplete or invalid."
            )
        else:
            print(f"\nLossless concatenation complete. Output: {output_path}")

    except Exception as e:
        print(f"An unexpected Python error occurred during processing: {e}")
        import traceback

        traceback.print_exc()
    finally:
        print("Cleaning up temporary files...")
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError as e_rm:
                    print(f"  Warning: Could not remove temp file {temp_file}: {e_rm}")
        if os.path.exists(list_file_path):
            try:
                os.remove(list_file_path)
            except OSError as e_rm:
                print(
                    f"  Warning: Could not remove temp list file {list_file_path}: {e_rm}"
                )
        if os.path.exists(temp_dir):
            try:
                if not os.listdir(temp_dir):
                    os.rmdir(temp_dir)
                else:
                    print(
                        f"  Temp directory {temp_dir} not empty. Manual cleanup may be needed."
                    )
            except OSError as e_rmdir:
                print(
                    f"  Warning: Could not remove temp directory {temp_dir}: {e_rmdir}"
                )


def _concat_encode(video_path, segments, output):
    sel_expr = "+".join(f"between(t,{ss},{to})" for ss, to in segments)

    cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        "6",  # adjust based on your CPU cores
        "-i",
        video_path,
        "-vf",
        f"select='{sel_expr}',setpts=N/FRAME_RATE/TB",
        "-af",
        f"aselect='{sel_expr}',asetpts=N/SR/TB",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",  # fastest preset with some size tradeoff
        "-crf",
        "23",  # reasonable quality/speed tradeoff
        "-c:a",
        "aac",
        "-b:a",
        "128k",  # avoid slow default VBR
        "-movflags",
        "+faststart",
        output,
    ]

    subprocess.run(cmd, check=True)


def concat_by_select(
    video_path, subtitles, indices, output, midpoints, *, use_gpu=False
):
    """
    - fast_copy=True  → key-frame-aligned copy-concat (blazing fast)
    - fast_copy=False → frame-accurate (slower), use_gpu toggles encoder
    """
    subtitles = merge_subtitles(subtitles, indices)
    print(subtitles)
    raw = _segments_from_subs(subtitles, midpoints)
    segments = _merge_segments(raw)
    print("will keep, ", segments)
    if not segments:
        raise ValueError("No non-empty segments to keep 🤷‍♂️")

    _concat_encode(video_path, segments, output)
    # _concat_lossless(video_path, segments, output)


def get_transcription(
    video: sieve.File,
    audio_path: sieve.File,
    silence_midpoints: List[float],
) -> List[Subtitle]:
    """
    Run Sieve whisper-v3 and return Subtitle blocks split on the supplied
    silence_midpoints.  Each Subtitle’s start/end snap to the nearest word
    boundary so we never cut a word in half.
    """
    # === 1. Transcribe ======================================================
    transcribe = sieve.function.get("sieve/transcribe")
    output = transcribe.run(
        video,
        "stable-ts-whisper-large-v3",
        True,  # word-level timestamps
        "auto",  # source_language
        "None",  # diarization_backend
        -1,
        -1,
        {},  # min/max speakers, vocab
        "None",
        "",  # translation backend / target lang
        "ffmpeg-silence",
        -1,  # min_segment_length
        0.3,  # min_silence_length
        0.2,  # vad_threshold
        0.8,  # pyannote threshold
        [""],  # chunks
        "None",  # denoise_backend
        "",  # initial_prompt
    )

    words = []
    for chunk in output:  # each chunk has "segments"
        for seg in chunk["segments"]:
            words.extend(seg["words"])  # each word: {"start", "end", "text"}
    if not words:
        return []  # nothing to do
    end_times = [w["end"] for w in words]
    cut_indices = [bisect_right(end_times, m) for m in silence_midpoints]
    cut_indices.append(len(words))
    subtitles: List[Subtitle] = []
    start_idx = 0
    for cut_idx in cut_indices:
        if cut_idx <= start_idx:
            continue  # two midpoints inside the same word gap → skip

        group = words[start_idx:cut_idx]
        subtitle_start = group[0]["start"]
        subtitle_end = group[-1]["end"] + 0.15
        subtitle_text = " ".join(w["word"] for w in group)

        subtitles.append(
            Subtitle(
                start=subtitle_start,
                end=subtitle_end,
                text=subtitle_text,
            )
        )

        start_idx = cut_idx  # next group starts with the next word

    return subtitles


def task_process_midpoints(video_url: str, audio_path: str):
    """Part 1: Download video"""
    print(audio_path)
    midpoints = detect_silence_midpoints(audio_path)
    print("Finished Part 1: Detect silence midpoints + download video")
    return midpoints


def get_youtube_title(video_url):
    response = requests.get(video_url)
    soup = BeautifulSoup(response.text, "html.parser")
    return soup.title.string


def get_subtitles_title(youtube_video_url: str):
    video_id = youtube_video_url.split("=")[1]
    transcript_raw = YouTubeTranscriptApi.get_transcript(video_id)
    subtitles = [
        Subtitle(
            text=subtitle["text"],
            start=float(subtitle["start"]),
            end=float(subtitle["start"]) + float(subtitle["duration"]),
        )
        for subtitle in transcript_raw
    ]
    title = get_youtube_title(youtube_video_url)
    return subtitles, title


def task_process_subtitles_and_segments(
    youtube_video_url: str, adhd_level: str, subtitles: List[Subtitle], title: str
):
    """Part 2: Download subtitles/title, then generate subtitle + pick segments"""
    print("Starting Part 2: Process subtitles and segments")
    # subtitles, title = get_subtitles_title(youtube_video_url)

    summary = generate_summary(subtitles, title)
    segments = pick_segments(subtitles, summary, title, adhd_level)

    # all_segments = range(len(subtitles))
    # segments = [
    #     segment for segment in all_segments if segment not in segments_to_remove
    # ]
    print(segments)
    print("Finished Part 2: Process subtitles and segments")
    return subtitles, segments


@sieve.function(
    name="create-adhd-video",  # Renamed to distinguish
    python_packages=[
        "python-dotenv",
        "openai",
        "webvtt-py",
        "beautifulsoup4",
        "youtube-transcript-api",
    ],
    system_packages=["ffmpeg"],
)
def create_adhd_video(
    youtube_video_url: str,
    adhd_level: Literal["relaxed", "normal", "hyper"] = "normal",
):
    print(
        f"Running parallel ADHD video creation for: {youtube_video_url} with level: {adhd_level}"
    )
    overall_start_time = time.time()
    audio_path, title, subtitles_path = download_video(youtube_video_url)
    # video_path = "tmp7e1_greu.mp4"
    # title = "How AI is Reinventing Software Business Models ft. Bret Taylor of Sierra"
    # subtitles_path = "subtitles.vtt"
    subtitles = load_subtitles(subtitles_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        # Submit tasks to the executor
        future_video_silences = executor.submit(
            task_process_midpoints, youtube_video_url, audio_path
        )
        future_subs_segments = executor.submit(
            task_process_subtitles_and_segments,
            youtube_video_url,
            adhd_level,
            subtitles,
            title,
        )

        # Retrieve results - these calls will block until the respective task is complete
        print("Waiting for parallel tasks to complete...")

        start_wait_video = time.time()
        midpoints = future_video_silences.result()  # Contains video.path
        print(
            f"Video download finished.. Time taken by task: {time.time() - start_wait_video:.2f}s (approx, depends on when it actually finished)"
        )
        print("# mids: ", len(midpoints) if midpoints else 0)
        print(midpoints[:20])

        start_wait_subs = time.time()
        subtitles, segments = (
            future_subs_segments.result()
        )  # title is also returned but not used in concat
        print(
            f"Subtitle processing and segment picking finished. Time taken by task: {time.time() - start_wait_subs:.2f}s (approx)"
        )
        # print("First 10 segments:", segments[:10] if segments else "No segments")

    print(
        f"All parallel parts completed. Total time for parallel section: {time.time() - overall_start_time:.2f}s"
    )

    output_path = (
        "video.mp4"  # Or a more unique name: f"adhd_video_{int(time.time())}.mp4"
    )

    print(f"Starting final concatenation to {output_path}...")
    concat_start_time = time.time()
    # concat_by_select(video_path, subtitles, segments, output_path, midpoints)

    subtitles = merge_subtitles(subtitles, segments)
    raw = _segments_from_subs(subtitles, midpoints)
    segments = _merge_segments(raw)
    print("will keep", segments)

    print(f"Concatenation finished. Time taken: {time.time() - concat_start_time:.2f}s")
    print(f"Total function execution time: {time.time() - overall_start_time:.2f}s")

    # return sieve.File(path=output_path)
    return convert_segments_to_dicts(segments)


# create_adhd_video("https://www.youtube.com/watch?v=sjeie9Y7AZk")
