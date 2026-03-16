import os
import warnings
import nltk
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from transformers import pipeline
from faster_whisper import WhisperModel

# Download pre-trained the NLTK sentence tokenizer model punkt 
nltk.download("punkt", quiet=True)
nltk.download('punkt_tab', quiet=True)

# Fix OpenMP library conflict on macOS
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Suppress urllib3 OpenSSL warning (LibreSSL vs OpenSSL on macOS)
warnings.filterwarnings("ignore", message=".*urllib3.*")

def transcribe_audio_file(path, result_path):
    """
    Transcribe audio file using faster-whisper, and write result to result_path
    """
    model_size = "tiny"

    # Device options: "cpu", "cuda", or "auto"
    # Compute type options: "int8" (fastest), "float16" (GPU), "float32" (CPU)
    device = "cpu"
    compute_type = "int8"  # Fast on CPU, use "float16" for GPU

    # Load model (models are cached after first download)
    model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
        num_workers=4,  # Use 1 worker to avoid multiprocessing issues on macOS
    )
 
    # Transcribe (VAD disabled for better MP3 compatibility)
    segments, info = model.transcribe(
        path,
        task="transcribe",  # Use "translate" to convert to English
        beam_size=5,  # Beam search size (lower = faster, higher = more accurate)
        # vad_filter=False,  # Disabled for MP3 compatibility
    )

    # Combine all segments into full text
    text = " ".join([segment.text for segment in segments])
    with open(result_path, "w") as f:
        f.write(text)

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

def summarize_text(full_text: str, min_length = 15, max_length=60):
    summarizer = pipeline("summarization", model="philschmid/bart-large-cnn-samsum")
    summary = summarizer(full_text, max_length=max_length, min_length=min_length, truncation=True)
    return summary
