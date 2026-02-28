#!/usr/bin/env python3

import argparse
import sys
from typing import Optional
import asr
import os

def process_audio_file(path):
    base_name, _ = os.path.splitext(path)
    asr.transcribe_audio_file(path, base_name + '.txt')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Podcast Organizer",
        epilog="Example: python main.py --src audiofile.mp3"
    )
    
    parser.add_argument(
        "--src", "-s",
        type=str,
        help="Path to an audio file to load and parse"
    )
    
    # parser.add_argument(
    #     "--output-dir", "-o",
    #     type=str,
    #     help="Path to an audio file to load and parse"
    # )
    
    args = parser.parse_args()
    
    if not args.src:
        print("You must specify a source file to process!")
        print("  python main.py --src audiofile.mp3")
        sys.exit(1)

    process_audio_file(args.src)
