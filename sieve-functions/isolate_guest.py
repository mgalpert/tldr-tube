import os
import time
import re
from typing import List, Dict, Tuple
import sieve
from dotenv import load_dotenv

load_dotenv()


def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from URL"""
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})(?:[?&]|$)", url)
    return match.group(1) if match else None


@sieve.function(
    name="isolate-podcast-guest",
    python_packages=[
        "python-dotenv",
    ],
    system_packages=["ffmpeg"],
)
def isolate_podcast_guest(
    youtube_video_url: str,
):
    """
    Process a podcast video to isolate only the guest speaker segments.
    
    This function:
    1. Downloads the video from YouTube
    2. Performs speaker diarization to identify different speakers
    3. Analyzes which speaker is likely the guest (vs host)
    4. Creates segments containing only the guest speaking
    
    Args:
        youtube_video_url: YouTube URL of the podcast video
        
    Returns:
        List of segments with guest-only timestamps
    """
    print(f"Processing podcast video: {youtube_video_url}")
    start_time = time.time()
    
    # Step 1: Download video from YouTube using Sieve's youtube-downloader
    print("Downloading video from YouTube...")
    youtube_downloader = sieve.function.get("sieve/youtube-downloader")
    
    # Download video with audio
    download_generator = youtube_downloader.run(
        url=youtube_video_url,
        download_type="video",
        resolution="720p",  # 720p is good balance for processing speed
        include_audio=True,
        start_time=0,
        end_time=-1,
        include_metadata=False,
        metadata_fields=[],
        include_subtitles=False,
        subtitle_languages=[],
        video_format="mp4",
        audio_format="mp3",
        subtitle_format="vtt"
    )
    
    # Extract the result from generator - need to consume all outputs
    download_results = []
    for output in download_generator:
        print(f"Download output: {output}")
        download_results.append(output)
    
    if not download_results:
        raise Exception("Failed to download video - no results returned")
    
    # The last output should contain the video
    download_result = download_results[-1]
    print(f"Final download result type: {type(download_result)}")
    print(f"Final download result: {download_result}")
    
    # The output is likely the file directly, not a dict
    video_file = download_result
    
    # Step 2: Download audio separately for diarization
    print("Downloading audio for diarization...")
    audio_generator = youtube_downloader.run(
        url=youtube_video_url,
        download_type="audio",
        resolution="highest-available",
        include_audio=True,
        start_time=0,
        end_time=-1,
        include_metadata=False,
        metadata_fields=[],
        include_subtitles=False,
        subtitle_languages=[],
        video_format="mp4",
        audio_format="wav",  # WAV format for better diarization
        subtitle_format="vtt"
    )
    
    # Extract the result from generator - need to consume all outputs
    audio_results = []
    for output in audio_generator:
        print(f"Audio download output: {output}")
        audio_results.append(output)
    
    if not audio_results:
        raise Exception("Failed to download audio - no results returned")
    
    # The last output should contain the audio
    audio_file = audio_results[-1]
    print(f"Final audio result type: {type(audio_file)}")
    print(f"Final audio result: {audio_file}")
    
    # Step 3: Perform speaker diarization
    print("Performing speaker diarization...")
    diarizer = sieve.function.get("sieve/pyannote-diarization")
    diarization_generator = diarizer.run(
        audio=audio_file,
        start_time=0,
        end_time=-1,
        min_speakers=-1,
        max_speakers=-1
    )
    
    # Collect all diarization outputs
    diarization_outputs = []
    for output in diarization_generator:
        diarization_outputs.append(output)
    
    print(f"Total diarization outputs: {len(diarization_outputs)}")
    
    # Parse diarization results
    speakers = parse_diarization_results(diarization_outputs)
    
    # Step 4: Identify host speaker (to exclude them)
    # First, let's see what speakers we have
    print(f"All speakers found: {list(speakers.keys())}")
    for speaker_id, segs in speakers.items():
        total_time = sum(end - start for start, end in segs)
        print(f"Speaker {speaker_id}: {len(segs)} segments, {total_time:.2f}s total")
    
    # Try to identify the host
    host_speaker = identify_host_speaker(speakers)
    
    # If we only have "unknown" speakers or similar issues, try a simpler approach
    if host_speaker == "unknown" or all(s == "unknown" for s in speakers.keys()):
        print("Warning: Could not properly identify speakers. Using fallback method.")
        # Assume SPEAKER_00 or SPEAKER_01 is the host (common in diarization)
        if "SPEAKER_00" in speakers:
            host_speaker = "SPEAKER_00"
        elif "SPEAKER_01" in speakers:
            host_speaker = "SPEAKER_01"
        else:
            # Just take the speaker with the most time as host
            host_speaker = max(speakers.items(), key=lambda x: sum(end - start for start, end in x[1]))[0]
    
    print(f"Identified host speaker: {host_speaker}")
    
    # Step 5: Create segments for all speakers EXCEPT the host
    guest_segments = create_all_guest_segments(speakers, host_speaker)
    
    print(f"Processing complete. Time taken: {time.time() - start_time:.2f}s")
    print(f"Found {len(guest_segments)} guest segments")
    
    if not guest_segments:
        print("No guest segments found!")
        return []
    
    # Sort segments by start time
    guest_segments.sort(key=lambda x: x["start"])
    
    print(f"Total guest speaking time: {sum(s['end'] - s['start'] for s in guest_segments):.2f}s")
    print(f"First few segments: {guest_segments[:5]}")
    
    # Prepare speaker statistics for frontend
    speaker_stats = []
    for speaker_id, segs in speakers.items():
        total_time = sum(end - start for start, end in segs)
        avg_segment_length = total_time / len(segs) if segs else 0
        speaker_stats.append({
            "id": speaker_id,
            "totalTime": total_time,
            "segmentCount": len(segs),
            "avgSegmentLength": avg_segment_length,
            "segments": [{"start": s, "end": e} for s, e in segs]
        })
    
    # Sort by total time (descending)
    speaker_stats.sort(key=lambda x: x["totalTime"], reverse=True)
    
    # Return both segments and speaker data
    return {
        "segments": guest_segments,
        "speakers": speaker_stats,
        "identifiedHost": host_speaker
    }


def parse_diarization_results(diarization_result) -> Dict[str, List[Tuple[float, float]]]:
    """
    Parse the diarization results into a dictionary of speakers and their time segments.
    
    Returns:
        Dictionary mapping speaker IDs to lists of (start, end) tuples
    """
    speakers = {}
    
    print(f"Diarization result type: {type(diarization_result)}")
    print(f"First few diarization segments: {list(diarization_result)[:5] if hasattr(diarization_result, '__iter__') else diarization_result}")
    
    # Handle both list and generator outputs
    segments = list(diarization_result) if hasattr(diarization_result, '__iter__') else [diarization_result]
    
    # Debug: print first few segments to understand format
    if segments:
        print(f"Total segments: {len(segments)}")
        print(f"First segment type: {type(segments[0])}")
        print(f"First segment: {segments[0]}")
        if hasattr(segments[0], '__dict__'):
            print(f"First segment attributes: {segments[0].__dict__}")
    
    for i, segment in enumerate(segments):
        if i < 5:  # Print first 5 segments for debugging
            print(f"Segment {i} type: {type(segment)}, content: {segment}")
        
        # Handle different possible formats
        if isinstance(segment, dict):
            speaker_id = segment.get("speaker_id", segment.get("speaker", segment.get("label", "unknown")))
            start = float(segment.get("start", segment.get("start_time", 0)))
            end = float(segment.get("end", segment.get("end_time", 0)))
        elif hasattr(segment, 'speaker') and hasattr(segment, 'start') and hasattr(segment, 'end'):
            # Handle object with attributes
            speaker_id = segment.speaker
            start = float(segment.start)
            end = float(segment.end)
        elif isinstance(segment, (list, tuple)) and len(segment) >= 3:
            # Handle tuple/list format (start, end, speaker)
            start = float(segment[0])
            end = float(segment[1])
            speaker_id = str(segment[2]) if len(segment) > 2 else "unknown"
        else:
            print(f"Unknown segment format: {segment}")
            print(f"Type: {type(segment)}")
            if hasattr(segment, '__dict__'):
                print(f"Attributes: {segment.__dict__}")
            continue
        
        if speaker_id not in speakers:
            speakers[speaker_id] = []
        speakers[speaker_id].append((start, end))
    
    print(f"Parsed speakers: {list(speakers.keys())}")
    for speaker, segs in speakers.items():
        print(f"Speaker {speaker}: {len(segs)} segments, total duration: {sum(end-start for start,end in segs):.2f}s")
    
    return speakers


def identify_host_speaker(speakers: Dict[str, List[Tuple[float, float]]]) -> str:
    """
    Identify which speaker is likely the host based on speaking patterns.
    
    Heuristics:
    1. Host usually speaks more total time than guests
    2. Host typically has more frequent, shorter segments (asking questions)
    3. Host often speaks first in podcasts
    
    Returns:
        Speaker ID of the likely host
    """
    if not speakers:
        return None
    
    speaker_stats = {}
    
    for speaker_id, segments in speakers.items():
        total_duration = sum(end - start for start, end in segments)
        avg_segment_length = total_duration / len(segments) if segments else 0
        num_segments = len(segments)
        first_appearance = min(start for start, end in segments) if segments else float('inf')
        
        speaker_stats[speaker_id] = {
            "speaker_id": speaker_id,
            "total_duration": total_duration,
            "avg_segment_length": avg_segment_length,
            "num_segments": num_segments,
            "first_appearance": first_appearance
        }
    
    # Sort by total duration (descending) - host likely speaks most
    sorted_by_duration = sorted(
        speaker_stats.values(),
        key=lambda x: x["total_duration"],
        reverse=True
    )
    
    # The host is typically the speaker with the most total speaking time
    # who also has many segments (asking questions frequently)
    host_candidate = sorted_by_duration[0]
    
    # Additional check: if the speaker with most time also has many short segments
    # and appears early, they're very likely the host
    if host_candidate["num_segments"] > 10 and host_candidate["first_appearance"] < 30:
        return host_candidate["speaker_id"]
    
    # Default to speaker with most total speaking time
    return sorted_by_duration[0]["speaker_id"]


def create_all_guest_segments(speakers: Dict[str, List[Tuple[float, float]]], 
                             host_speaker: str) -> List[Dict[str, float]]:
    """
    Create segment list containing all speakers EXCEPT the host.
    
    Returns:
        List of dictionaries with 'start' and 'end' keys
    """
    guest_segments = []
    
    # Collect segments from all speakers except the host
    for speaker_id, segments in speakers.items():
        if speaker_id != host_speaker:
            print(f"Including segments from speaker: {speaker_id}")
            for start, end in segments:
                # Add small buffer to ensure clean cuts
                segment = {
                    "start": max(0, start - 0.1),
                    "end": end + 0.1
                }
                guest_segments.append(segment)
        else:
            print(f"Excluding host speaker: {speaker_id}")
    
    # Sort by start time
    guest_segments.sort(key=lambda x: x["start"])
    
    # Merge overlapping or very close segments (within 1 second)
    merged_segments = []
    for segment in guest_segments:
        if merged_segments and segment["start"] - merged_segments[-1]["end"] < 1.0:
            # Merge with previous segment
            merged_segments[-1]["end"] = max(merged_segments[-1]["end"], segment["end"])
        else:
            merged_segments.append(segment)
    
    return merged_segments


