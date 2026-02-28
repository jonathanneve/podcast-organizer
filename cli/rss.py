# RSS feed handler

import feedparser
import requests
from os import path

feed = feedparser.parse('https://feeds.megaphone.fm/SIXMSB5088139739')
latest_episode = feed.entries[0]
print(f'Latest episode: {latest_episode.title}\n')
print(f'Description: {latest_episode.description}\n')
print('Downloading audio...')
print(latest_episode.enclosures[0])

file_url = str(latest_episode.enclosures[0].href)
file_name = f'./{latest_episode.guid}.mp3'
with requests.get(file_url, stream=True) as r:
    r.raise_for_status()
    with open(file_name, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

print('Transcribing audio...')