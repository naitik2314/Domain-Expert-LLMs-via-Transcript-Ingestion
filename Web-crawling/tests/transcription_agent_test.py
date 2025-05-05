from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

def test_fetch(video_id: str):
    """
    Fetches and prints the first 500 characters of the English transcript
    """
    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id=video_id, languages=['en'])
        text = " ".join(seg['text'] for seg in segments)
        print(f"Transcript for {video_id} (first 500 chars):\n\n{text[:500]}...\n")
    except (TranscriptsDisabled, NoTranscriptFound):
        print(f"No English transcript available for {video_id}")
    except Exception as e:
        print(f"Error fetching for {video_id}: {e}")

if __name__ == "__main__":
    sample_id = "2BB-VrxgdG4"
    test_fetch(sample_id)