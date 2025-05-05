# crawl_and_fetch_all.py

import asyncio
import os
import re
import json
import sqlite3
from datetime import datetime

from dotenv import load_dotenv
from pydantic import SecretStr

from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, BrowserConfig
from browser_use.browser.browser import Browser
from browser_use.browser.context import BrowserContextConfig
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

# --- LOAD GEMINI CREDENTIALS ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is not set")

# --- INSTANTIATE GEMINI LLM & BROWSER ---
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-exp",
    api_key=SecretStr(api_key)
)

browser = Browser(
    config=BrowserConfig(
        new_context_config=BrowserContextConfig(
            viewport_expansion=0,
        )
    )
)

# --- CONFIGURATION ---
SEARCH_QUERY = "dating apps chat tips"
DB_PATH      = "dating_transcripts.db"

# --- SETUP SQLITE (videos + transcripts tables) ---
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS videos (
    video_id   TEXT PRIMARY KEY,
    scraped_at TIMESTAMP NOT NULL
)
""")
c.execute("""
CREATE TABLE IF NOT EXISTS transcripts (
    video_id   TEXT PRIMARY KEY,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    language   TEXT,
    text       TEXT
)
""")
conn.commit()

# --- HARVEST VIDEO IDs VIA YOUTUBE SEARCH (first page only) ---
async def harvest_youtube_links() -> list[str]:
    search_url = f"https://www.youtube.com/results?search_query={SEARCH_QUERY}"
    task = f"""
1) Go to {search_url}
2) Extract every href matching /watch\\?v=[A-Za-z0-9_-]{{11}}/ from the initial page load
3) Return a JSON array of unique 11-character video IDs
"""
    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        max_actions_per_step=3  # limited actions: navigate + extract
    )
    # allow up to 10 LLM steps (should finish immediately)
    raw = await agent.run(max_steps=10)

    # Parse JSON array if possible, otherwise regex
    try:
        vids = raw.json()
    except Exception:
        vids = re.findall(r'"([A-Za-z0-9_-]{11})"', str(raw))

    unique_vids = list(dict.fromkeys(vids))

    # Store scraped IDs in the videos table
    now = datetime.utcnow().isoformat()
    for vid in unique_vids:
        c.execute(
            "INSERT OR IGNORE INTO videos (video_id, scraped_at) VALUES (?, ?)",
            (vid, now)
        )
    conn.commit()

    return unique_vids

# --- FETCH & STORE TRANSCRIPT ---
def fetch_and_store(video_id: str) -> bool:
    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
        text = " ".join(seg["text"] for seg in segments)
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable) as e:
        print(f"⚠️  Skipping {video_id}: {e.__class__.__name__}")
        return False

    c.execute(
        "REPLACE INTO transcripts (video_id, language, text) VALUES (?, ?, ?)",
        (video_id, "en", text)
    )
    conn.commit()
    return True

# --- MAIN ORCHESTRATION ---
async def main():
    print("🔍 Scouring YouTube (first page only) for dating videos…")
    video_ids = await harvest_youtube_links()
    print(f"▶️  Harvested {len(video_ids)} unique video IDs.")

    for vid in video_ids:
        ok = fetch_and_store(vid)
        status = "✅ Transcript stored" if ok else "⚠️  No English captions"
        print(f"{status} for {vid}")

if __name__ == "__main__":
    asyncio.run(main())
