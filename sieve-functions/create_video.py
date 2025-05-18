# from google import genai
# from google.genai import types
import os
import re
import time
from typing import List, Literal

import openai
import requests
import sieve
import webvtt
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from get_subtitles import get_grouped_subtitles
from segment_selection import generate_summary, pick_segments
from youtube_transcript_api import YouTubeTranscriptApi

load_dotenv()

openai_client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://api.openai.com/v1",
)

gemini_client = openai.OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)


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


def filter_included(included_indicies: List[int], len_subs: int) -> List[int]:
    return [num for num in included_indicies if num < len_subs]


def get_youtube_video_id(url: str):
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:[?&]|$)", url)
    return match.group(1) if match else None


def merge_subtitles(
    subtitles: List[Subtitle], include_indices: List[int]
) -> List[Subtitle]:
    print(len(subtitles))
    indices_filtered = filter_included(include_indices, len(subtitles))
    print("filtered", indices_filtered)

    included = sorted(
        [subtitles[i] for i in sorted(set(indices_filtered))],
        key=lambda s: s.start,
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


def convert_segments_to_dicts(subtitles: List[Subtitle]) -> List[dict]:
    """
    Convert Subtitle objects to dicts while making sure segments don’t overlap.

    If a segment’s start time is ≤ the end time of the previous segment,
    bump its start to `prev_end + 0.1`.

    Returns
    -------
    List[dict]
        Each dict has “start” and “end” keys (floats, seconds).
    """
    segments: List[dict] = []
    prev_end = float("-inf")

    # If the input order isn’t guaranteed, uncomment the next line:
    # subtitles = sorted(subtitles, key=lambda s: s.start)

    for sub in subtitles:
        start = sub.start
        if start <= prev_end:  # overlap detected
            start = prev_end + 0.1  # push start 0.1 s past prev_end

        segments.append({"start": start, "end": sub.end})
        prev_end = segments[-1]["end"]  # use (possibly unchanged) end as new boundary

    return segments


def get_youtube_title(video_url):
    response = requests.get(video_url)
    soup = BeautifulSoup(response.text, "html.parser")
    return soup.title.string


def get_subtitles_title(youtube_video_url: str):
    video_id = get_youtube_video_id(youtube_video_url)
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


def select_segments(
    youtube_video_url: str,
    adhd_level: str,
    subtitles: List[Subtitle],
    title: str,
    mode: Literal["fast", "quality"],
):
    summary = generate_summary(subtitles, title)
    segments = pick_segments(subtitles, summary, title, adhd_level, mode)
    print(segments)
    return segments


@sieve.function(
    name="create-tldr-video",  # Renamed to distinguish
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
    mode: Literal["fast", "quality"],
    adhd_level: Literal["relaxed", "normal", "hyper"] = "normal",
):
    print(
        f"Running parallel ADHD video creation for: {youtube_video_url} with level: {adhd_level}"
    )
    overall_start_time = time.time()
    # Testing video:
    # video_path = "tmp7e1_greu.mp4"
    # title = "How AI is Reinventing Software Business Models ft. Bret Taylor of Sierra"
    # subtitles_path = "subtitles.vtt"
    subtitles, title = get_grouped_subtitles(youtube_video_url)

    segments = select_segments(youtube_video_url, adhd_level, subtitles, title, mode)
    output_path = "video.mp4"

    print(f"Starting final concatenation to {output_path}...")
    concat_start_time = time.time()
    # concat_by_select(video_path, subtitles, segments, output_path, midpoints)

    subtitles = merge_subtitles(subtitles, segments)
    print("will keep", subtitles)

    print(f"Concatenation finished. Time taken: {time.time() - concat_start_time:.2f}s")
    print(f"Total function execution time: {time.time() - overall_start_time:.2f}s")

    # return sieve.File(path=output_path)
    return convert_segments_to_dicts(subtitles)


# create_adhd_video("https://www.youtube.com/watch?v=sjeie9Y7AZk")
