import sys
import argparse
import nltk
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# Download pre-trained the NLTK sentence tokenizer model punkt 
nltk.download("punkt", quiet=True)
nltk.download('punkt_tab', quiet=True)

def segment_text(text):
    # First, let's split up the text into individual sentences
    sentences = nltk.sent_tokenize(text)

    # Now, we need to calculate embedding vectors to represent the semantic
    # meaning of each sentence
    # For that, we use all-MiniLM-L6-v2, a local pre-trained sentence embedding model
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = embedding_model.encode(sentences)

    # We can now figure out the topic boundaries by calculating the average embeddings
    # across a window of consecutive sentences, and then calculating the cosine similarity of pairs
    # of such windows
    window_size = 5
    threshold = 0.2
    boundaries = [0]
    for i in range(0, len(sentences) - window_size * 2):
        window1 = embeddings[i : i + window_size].mean(axis=0)
        window2 = embeddings[i + window_size : i + 2 * window_size].mean(axis=0)
        similarity = cosine_similarity(np.array([window1]), np.array([window2]))[0][0]
    
        if similarity < threshold:
            boundaries.append(i)

    # Add last sentence as the final boundary
    boundaries.append(len(sentences))

    # Group up boundaries into a list of segments
    segments_boundaries = zip(boundaries, boundaries[1:])
    segments = [" ".join(sentences[start:end]) for start, end in segments_boundaries]
    return segments


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Podcast Organizer",
        epilog="Example: python summarize.py -f text_file.txt"
    )

    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Path to a text file to summarize"
    )

    args = parser.parse_args()

    if not args.file:
        print("You must specify a source file to process!")
        print("  python summarize.py -f text_file.txt")
        sys.exit(1)
    
    with open(args.file, "r") as f:
        text = f.read()
    topics = segment_text(text)

    print(topics)
    print(f'{len(topics)} detected!')
