import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Literal, Tuple

import openai
from dotenv import load_dotenv

load_dotenv()

openai_client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://api.openai.com/v1",
)

gemini_client = openai.OpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)


def get_adhd_length(adhd_level: Literal["relaxed", "normal", "hyper"]) -> str:
    if adhd_level == "normal":
        return "1/4th to 1/5th "
    if adhd_level == "hyper":
        return "1/8th to 1/10th "
    if adhd_level == "relaxed":
        return "1/2 to 1/3rd "


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


SYSTEM_PROMPT = """
You are an AI editor that takes transcripts ofevideos and RUTHLESSLY cuts out any
fluff, and details that aren't relevant to the major points of the video. The goal is
to take a video and make it ADHD friendly, so you should aim for an 75-85% reduction in video length (SO YOU ARE POTENTIALLY CUTTING A LOT).
You are kind of just like a turbo ADHD brain you just wanna get the point of the video and get OUT!
You will be given a chunk of subtitle segments from the video with their corresponding indices.
This chunk is just one section of the whole video.
Your goal is to select which indices to include in the video to remove the fluff, while also keeping things coherent.

For example: 

0. "transcript text segment 1..."
1. "transcript text segment 2..."
2. "transcript text segment 3..."


Additionally you will be given a summary of the video which encapsulates the main points that you need 
to include in the video. Also you will be given the title of the video, this is the main thing people 
who are watching the video are trying to figure out.

PLEASE return your response in a JSON array of just the indices of the most important transcript segments
in the video. For example: 

"result": {
    [1, 2]
}
"""


def pick_segments(
    subtitles: List[Subtitle],
    summary: str,
    title: str,
    adhd_level: int,
    mode: Literal["fast", "quality"],
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

    def _call_model(batch: List[Tuple[int, Subtitle]], chunk_num: int) -> List[int]:
        prompt = _build_prompt(batch, chunk_num)
        if mode == "fast":
            completion = openai_client.chat.completions.create(
                # model="gemini-2.5-flash-preview-04-17",
                model="gpt-4o",
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
        else:
            completion = gemini_client.chat.completions.create(
                model="gemini-2.5-pro-preview-05-06",
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

        data_raw = safe_json(completion.choices[0].message.content)
        # print(data)
        data = data_raw["result"]
        print(f"Chunk {chunk_num} result, ", data)
        return data if isinstance(data, list) else data.get("indices", [])

    # ────────── launch requests in parallel ──────────
    chosen: List[int] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, total_chunks)) as pool:
        futures = {
            pool.submit(_call_model, batch, i + 1): i for i, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            chosen.extend(map(int, future.result()))

    # remove duplicates introduced by the 25-line overlap
    return sorted(set(chosen))
