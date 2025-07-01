import sieve
from typing import List, Dict

@sieve.function(
    name="filter-speakers",
    python_packages=[],
)
def filter_speakers(
    all_speakers: List[Dict],
    excluded_speaker_ids: List[str]
) -> List[Dict[str, float]]:
    """
    Filter segments based on excluded speakers.
    
    Args:
        all_speakers: List of speaker data with segments
        excluded_speaker_ids: List of speaker IDs to exclude
        
    Returns:
        List of segments excluding the specified speakers
    """
    filtered_segments = []
    
    for speaker in all_speakers:
        if speaker["id"] not in excluded_speaker_ids:
            # Include this speaker's segments
            for segment in speaker["segments"]:
                filtered_segments.append({
                    "start": max(0, segment["start"] - 0.1),
                    "end": segment["end"] + 0.1
                })
    
    # Sort by start time
    filtered_segments.sort(key=lambda x: x["start"])
    
    # Merge overlapping segments
    merged_segments = []
    for segment in filtered_segments:
        if merged_segments and segment["start"] - merged_segments[-1]["end"] < 1.0:
            merged_segments[-1]["end"] = max(merged_segments[-1]["end"], segment["end"])
        else:
            merged_segments.append(segment)
    
    return merged_segments