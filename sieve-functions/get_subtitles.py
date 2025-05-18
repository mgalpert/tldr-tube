import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple

import openai
import sieve
import webvtt
from dotenv import load_dotenv

load_dotenv()

openai_client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://api.openai.com/v1",
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


def download_video(url):
    download_type = "subtitles"
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
    subtitle_format = "json3"

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
        subtitle_format,
    )

    for index, output_object in enumerate(output):
        if index == 0:
            title = output_object["title"]
        elif index == 1:
            subtitles_path = output_object["en"].path

    return title, subtitles_path


def load_subtitles_json3(subtitles_path: str) -> List[Subtitle]:
    """
    Parse a YouTube json3 transcript (one file per language) and return
    a list of word-level Subtitle objects, sorted by start time.
    """
    data = json.loads(Path(subtitles_path).read_text(encoding="utf-8"))

    subs: List[Subtitle] = []

    for event in data.get("events", []):
        t_start_ms: int | None = event.get("tStartMs")
        if t_start_ms is None or "segs" not in event:  # style / window events
            continue

        segs = event["segs"]

        for i, seg in enumerate(segs):
            word = seg.get("utf8", "").strip()
            if not word:  # ignore empty/whitespace
                continue

            offset_ms = seg.get("tOffsetMs", 0)
            start = (t_start_ms + offset_ms) / 1000.0  # → seconds

            # ───── determine an end time ─────────────────────
            if i + 1 < len(segs):  # next word inside same event
                next_offset = segs[i + 1].get("tOffsetMs", offset_ms)
                end = (t_start_ms + next_offset) / 1000.0
            else:  # last word in this event
                dur_ms = event.get("dDurationMs")
                if dur_ms is not None:
                    end = (t_start_ms + dur_ms) / 1000.0
                else:  # fallback: tiny padding
                    end = start + 0.15

            subs.append(Subtitle(word, start, end))

    # Safety: keep chronological order
    subs.sort(key=lambda s: s.start)
    return subs


def load_subtitles(subtitles_path: str) -> List[Subtitle]:
    return [
        Subtitle(
            text=cap.text,
            start=cap.start_in_seconds,  # Use float attribute
            end=cap.end_in_seconds,  # Use float attribute
        )
        for cap in webvtt.read(subtitles_path)
    ]


_PUNCT = ".?!,:;-—"  # feel free to tweak / extend


def group_subtitles_by_punctuation(
    subs: List[Subtitle],
    punctuation: str = _PUNCT,
    *,
    offset: float = 0.2,
    max_words: int = 10,
) -> List[Subtitle]:
    """
    Combine word-level Subtitle cues into phrase/sentence-level cues.
    A new group is closed whenever:
      - the final character of the current word is in `punctuation`, or
      - the group reaches `max_words` length.
    Each group’s start time is shifted forward by `offset` seconds.
    """
    grouped: List[Subtitle] = []
    if not subs:
        return grouped

    buffer: List[str] = []
    grp_start: float | None = None
    grp_end: float = 0

    for cue in subs:
        if grp_start is None:  # starting a new group
            grp_start = cue.start

        buffer.append(cue.text)
        grp_end = cue.end

        should_close = (cue.text and cue.text[-1] in punctuation) or len(
            buffer
        ) >= max_words

        if should_close:
            grouped.append(
                Subtitle(
                    text=" ".join(buffer),
                    start=grp_start + offset,
                    end=grp_end,
                )
            )
            buffer.clear()
            grp_start = None

    # flush any remaining buffer
    if buffer:
        grouped.append(
            Subtitle(
                text=" ".join(buffer),
                start=(grp_start if grp_start is not None else subs[0].start) + offset,
                end=grp_end,
            )
        )

    return grouped


SYSTEM_PROMPT = """
You are an AI punctuation/phrase-boundary restorer.

• **Input you receive**  
  A chunk of consecutive *words* from a transcript, each prefixed by its 0-based *global* index, e.g.:

    17. I
    18. am
    19. 23
    20. years
    21. old
    22. I
    23. like
    24. pie

  The chunk is only part of the full transcript.  Chunks may overlap, so you might
  see the same word index in two chunks.

• **Task**  
  Decide after which words a phrase or sentence naturally ends (where you would
  place “.”, “?”, “!”, or “,” that closes a clause).  
  Return **only** the indices of those *final* words.

  Using the example above, the correct output is:

      "result": [21, 24]

• **Output format**  
  A JSON object with a single key `result` whose value is an array of integers:

      {
        "result": [21, 24]
      }

  – Do **not** wrap the array in any other keys.  
  – Do **not** include explanations or extra text.  
  – If no phrase ends in this chunk, return an empty array.

• **Guidelines**  
  – Treat abbreviations (“U.S.”, “Dr.”) as *not* ending a phrase.  
  – A phrase should be long enough to be understood on its own; avoid splitting
    on every single word.  
  – Never propose an index that is **not** present in the chunk you were given.
"""


def pick_punctuation(
    subtitles: List[Subtitle],
    chunk_size: int = 100,  # ← slide-window length
    overlap: int = 25,  # ← lines shared with the previous chunk
    max_workers: int = 20,
) -> List[int]:
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
            f"Chunk {chunk_num} of {total_chunks}\n\n"
            "Here are word-level subtitles:\n"
            f"{joined}\n\n"
            "Return the JSON described in the system prompt."
        )

    def _call_model(batch: List[Tuple[int, Subtitle]], chunk_num: int) -> List[int]:
        prompt = _build_prompt(batch, chunk_num)
        # print(prompt)
        completion = openai_client.chat.completions.create(
            # model="gemini-2.5-flash-preview-04-17",
            model="gpt-4o",
            # model="gemini-2.5-pro-preview-05-06",
            # reasoning_effort="medium",
            messages=[
                {
                    "role": "user",
                    "content": SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        data_raw = safe_json(completion.choices[0].message.content)
        # print(data)
        data = data_raw["result"]
        # print(f"Chunk {chunk_num} result, ", data)
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


def group_by_indices(subtitles: List[Subtitle], indices: List[int]) -> List[Subtitle]:
    if not subtitles or not indices:
        return []

    indices = sorted(set(i for i in indices if 0 <= i < len(subtitles)))

    new_subtitles: List[Subtitle] = []
    cur_start_idx = 0

    for end_idx in indices:
        # grab the span [cur_start_idx .. end_idx]
        span = subtitles[cur_start_idx : end_idx + 1]

        # join text and build combined cue
        text = " ".join(s.text for s in span)
        start = span[0].start
        end = span[-1].end
        new_subtitles.append(Subtitle(text, start, end))

        # next span starts after the current end-index
        cur_start_idx = end_idx + 1

    return new_subtitles


def get_grouped_subtitles(url: str) -> List[Subtitle]:
    title, vtt_path = download_video(url)
    word_level = load_subtitles_json3(vtt_path)  # each cue == one token
    # print("word level", word_level)
    punctuation_ends = pick_punctuation(word_level)
    # print(punctuation_ends)

    sentence_level = group_by_indices(word_level, punctuation_ends)
    return sentence_level, title


# print(get_grouped_subtitles("https://www.youtube.com/watch?v=D29swWwYXkI"))
# print(get_grouped_subtitles("https://www.youtube.com/watch?v=MzkgWDCucNY"))
