from bisect import bisect_left, bisect_right
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

# from google import genai
# from google.genai import types
import os
import json
from concurrent.futures import ThreadPoolExecutor


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
    download_type = "video"
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
            video_path = output_object.path
        elif index == 2:
            subtitles_path = output_object["en"].path

    return video_path, subtitles_path, title


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
to take a video and make it ADHD friendly, so you should aim for an 75-85% reduction in video length
(SO YOU ARE POTENTIALLY CUTTING A LOT). Make sure that you also still ensure that any thoughts are complete.
You are kind of just like a turbo ADHD brain you just wanna get the point of the video and get OUT!
You will be given a list of audio segments with their corresponding indices. 
Your goal is to select which indices to include in the video to remove 
the fluff, while also keeping things coherent, with each segment representing a complete thought.

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


def pick_segments(subtitles: List[Subtitle], summary: str, title: str, adhd_level):
    joined_subs = "\n".join(f"{i}. {obj.text}" for i, obj in enumerate(subtitles))
    user_prompt = f"""
    Please reduce this transcript:
    {joined_subs}
    -----------------------------------------
    Title:   {title}
    Summary: {summary}
    """

    print(user_prompt)

    completion = openai_client.chat.completions.create(
        # model="gemini-2.5-pro-preview-05-06",
        # model="gemini-2.5-flash-preview-04-17",
        model="gpt-4.5-preview",
        # model="gpt-4o",
        # model="gemini-2.0-flash",
        # reasoning_effort="medium",
        messages=[
            {
                "role": "user",
                "content": SYSTEM_PROMPT.replace(
                    "VIDEO_REDUCTION_AMOUNT", get_adhd_length(adhd_level)
                ),
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        response_format={"type": "json_object"},
    )

    return completion.choices[0].message.content


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
    video_path: str, silence_duration: float = 0.1
) -> List[float]:
    mid_start = time.time()
    cmd = [
        "ffmpeg",
        "-i",
        video_path,
        "-vn",
        "-af",
        f"silencedetect=noise=-30dB:d={silence_duration}",
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


def _concat_copy(src, segments, out):
    from pathlib import Path
    import tempfile, subprocess, shutil

    tmp = Path(tempfile.mkdtemp())
    listfile = tmp / "files.txt"

    entries = []
    for i, (ss, to) in enumerate(segments):
        cut = tmp / f"cut{i:04d}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(ss),
                "-to",
                str(to),
                "-i",
                src,
                "-c",
                "copy",
                "-reset_timestamps",
                "1",  # <── changed
                "-y",
                cut,
            ],
            check=True,
        )
        entries.append(f"file '{cut}'")

    listfile.write_text("\n".join(entries))

    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            listfile,
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            "-y",
            out,
        ],
        check=True,
    )

    shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------
# 2B.  Frame-accurate re-encode (GPU if you have one)
# ------------------------------------------------------------------
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


def task_process_midpoints(video_path: str):
    """Part 1: Download video"""
    midpoints = detect_silence_midpoints(video_path)
    print("Finished Part 1: Detect silence midpoints + download video")
    return midpoints


def task_process_subtitles_and_segments(
    subtitles_path: str, title: str, adhd_level: str
):
    """Part 2: Download subtitles/title, then generate subtitle + pick segments"""
    print("Starting Part 2: Process subtitles and segments")
    subtitles = load_subtitles(subtitles_path)

    summary = generate_summary(subtitles, title)
    raw_segments_data = pick_segments(subtitles, summary, title, adhd_level)
    segments = safe_json(raw_segments_data)["result"]
    # all_segments = range(len(subtitles))
    # segments = [
    #     segment for segment in all_segments if segment not in segments_to_remove
    # ]
    print(segments)
    print("Finished Part 2: Process subtitles and segments")
    return subtitles, segments


@sieve.function(
    name="create-adhd-video",  # Renamed to distinguish
    python_packages=["python-dotenv", "openai", "webvtt-py"],
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
    video_path, subtitles_path, title = download_video(youtube_video_url)

    with ThreadPoolExecutor(max_workers=2) as executor:
        # Submit tasks to the executor
        future_video_silences = executor.submit(task_process_midpoints, video_path)
        future_subs_segments = executor.submit(
            task_process_subtitles_and_segments, subtitles_path, title, adhd_level
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
    concat_by_select(video_path, subtitles, segments, output_path, midpoints)

    print(f"Concatenation finished. Time taken: {time.time() - concat_start_time:.2f}s")
    print(f"Total function execution time: {time.time() - overall_start_time:.2f}s")

    return sieve.File(path=output_path)


# create_adhd_video("https://www.youtube.com/watch?v=sjeie9Y7AZk")
