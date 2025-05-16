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
from get_subtitles import get_grouped_subtitles
from segment_selection import generate_summary, pick_segments


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


def convert_segments_to_dicts(subtitles: List[Subtitle]):
    return [{"start": subtitle.start, "end": subtitle.end} for subtitle in subtitles]


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


def select_segments(
    youtube_video_url: str, adhd_level: str, subtitles: List[Subtitle], title: str
):
    summary = generate_summary(subtitles, title)
    segments = pick_segments(subtitles, summary, title, adhd_level)
    print(segments)
    return segments


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
    # Testing video:
    # video_path = "tmp7e1_greu.mp4"
    # title = "How AI is Reinventing Software Business Models ft. Bret Taylor of Sierra"
    # subtitles_path = "subtitles.vtt"
    subtitles, title = get_grouped_subtitles(youtube_video_url)

    segments = select_segments(youtube_video_url, adhd_level, subtitles, title)
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
