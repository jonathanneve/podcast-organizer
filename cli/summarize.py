import sys
import argparse
from transformers import pipeline

def summarize_text(full_text: str, min_length = 15, max_length=60):
    summarizer = pipeline("summarization", model="philschmid/bart-large-cnn-samsum")
    summary = summarizer(full_text, max_length=max_length, min_length=min_length, truncation=True)
    return summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Podcast Organizer",
        epilog="Example: python topic_segmentation.py -f text_file.txt"
    )

    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Path to a text file to segment into topics"
    )

    args = parser.parse_args()

    if not args.file:
        print("You must specify a source file to process!")
        print("  python topic_segmentation.py -f text_file.txt")
        sys.exit(1)
    
    with open(args.file, "r") as f:
        text = f.read()
    print(summarize_text(text))
