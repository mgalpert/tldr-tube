import json
from pathlib import Path
from typing import List

import sieve
import webvtt


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


def download_video(url):
    download_type = "subtitles"
    resolution = "720p"
    include_audio = True
    start_time = 0
    end_time = -1
    include_metadata = True
    metadata_fields = ["title", "duration"]
    include_subtitles = True
    subtitle_format = "json3"
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
        subtitle_format,
        subtitle_languages,
        video_format,
        audio_format,
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
    offset: float = 0.2,  # ← add an offset parameter (default 0.2 s)
) -> List[Subtitle]:
    """
    Combine word-level Subtitle cues into phrase/sentence-level cues.
    A new group is closed whenever the **final character** of the current word
    is in `punctuation`.  Each group’s start time is shifted forward by
    `offset` seconds.

    Returns
    -------
    List[Subtitle]
        Phrase/sentence-level cues with adjusted start times.
    """
    grouped: List[Subtitle] = []
    if not subs:
        return grouped

    buffer: List[str] = []
    grp_start: float | None = None

    for cue in subs:
        if grp_start is None:  # starting a new group
            grp_start = cue.start

        buffer.append(cue.text)

        if cue.text and cue.text[-1] in punctuation:  # close the group
            grouped.append(
                Subtitle(
                    text=" ".join(buffer),
                    start=grp_start + offset,  # ← shift start
                    end=cue.end,
                )
            )
            buffer.clear()
            grp_start = None

    # flush any trailing words lacking punctuation
    if buffer:
        grouped.append(
            Subtitle(
                text=" ".join(buffer),
                start=(grp_start if grp_start is not None else subs[0].start) + offset,
                end=subs[-1].end,
            )
        )

    return grouped


def get_grouped_subtitles(url: str) -> List[Subtitle]:
    title, vtt_path = download_video(url)
    word_level = load_subtitles_json3(vtt_path)  # each cue == one token
    sentence_level = group_subtitles_by_punctuation(word_level)
    return sentence_level, title


# print(get_grouped_subtitles("https://www.youtube.com/watch?v=D29swWwYXkI"))
