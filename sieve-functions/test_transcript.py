import requests
from bs4 import BeautifulSoup

# from youtube_transcript_api import YouTubeTranscriptApi


# class Subtitle:
#     def __init__(self, text: str, start: float, end: float):  # Changed str to float
#         self.text = text
#         self.start = start
#         self.end = end

#     # nice-looking representations
#     def __str__(self):
#         # This formatting will now work correctly as start/end are floats
#         return f"{self.start:.3f} – {self.end:.3f} : {self.text}"

#     __repr__ = __str__


# youtube_video_url = "https://www.youtube.com/watch?v=Qc_kEyLsXH0"
# video_id = youtube_video_url.split("=")[1]
# transcript_raw = YouTubeTranscriptApi.get_transcript(video_id)
# subtitles = [
#     Subtitle(
#         text=subtitle["text"],
#         start=float(subtitle["start"]),
#         end=float(subtitle["start"]) + float(subtitle["duration"]),
#     )
#     for subtitle in transcript_raw
# ]
# print(subtitles)


def get_youtube_title(video_url):
    response = requests.get(video_url)
    soup = BeautifulSoup(response.text, "html.parser")
    return soup.title.string


print(get_youtube_title("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
