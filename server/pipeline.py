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

def transcribe_audio_file(path, result_path) -> tuple[int, list[tuple[float, str]]]:
    """
    Transcribe audio file using faster-whisper, and write result to result_path.
    Returns (duration_seconds, timestamped_segments) where each segment is (start_seconds, text).
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

    # Collect segments with timestamps
    timestamped = [(seg.start, seg.text) for seg in segments]

    # Combine all segments into full text
    text = " ".join([t for _, t in timestamped])
    with open(result_path, "w") as f:
        f.write(text)

    return int(info.duration), timestamped

def segment_text(text: str, timestamped_segments: list[tuple[float, str]] | None = None) -> list[dict]:
    """
    Segments text into topics based on semantic similarity.
    Returns a list of dicts with 'text' and 'start_time' (seconds, or None if no timestamps).
    """

    # First, let's split up the text into individual sentences
    sentences = nltk.sent_tokenize(text)

    # Map each sentence to an approximate audio timestamp by tracking
    # character offsets through the original text
    sentence_timestamps: list[float | None] = [None] * len(sentences)
    if timestamped_segments:
        # Build a list of (char_offset, start_time) from segments
        char_offsets: list[tuple[int, float]] = []
        pos = 0
        for start_time, seg_text in timestamped_segments:
            idx = text.find(seg_text.strip(), pos)
            if idx >= 0:
                char_offsets.append((idx, start_time))
                pos = idx + len(seg_text.strip())

        # For each sentence, find its position in the text and look up the closest timestamp
        for i, sent in enumerate(sentences):
            sent_pos = text.find(sent)
            if sent_pos >= 0 and char_offsets:
                # Find the last segment that starts at or before this sentence
                ts = char_offsets[0][1]
                for offset, t in char_offsets:
                    if offset <= sent_pos:
                        ts = t
                    else:
                        break
                sentence_timestamps[i] = ts

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

    # Group up boundaries into a list of segments with text and start time for each
    segments_boundaries = zip(boundaries, boundaries[1:])
    results = []
    for start, end in segments_boundaries:
        results.append({
            "text": " ".join(sentences[start:end]),
            "start_time": int(sentence_timestamps[start]) if sentence_timestamps[start] is not None else None,
        })
    return results

_bart_tokenizer = None
_bart_model = None

def _get_bart_model():
    from transformers import BartTokenizer, BartForConditionalGeneration
    global _bart_tokenizer, _bart_model
    if _bart_tokenizer is None:
        _bart_tokenizer = BartTokenizer.from_pretrained("philschmid/bart-large-cnn-samsum")
        _bart_model = BartForConditionalGeneration.from_pretrained("philschmid/bart-large-cnn-samsum")
    assert _bart_tokenizer is not None and _bart_model is not None
    return _bart_tokenizer, _bart_model

def summarize_text(full_text: str, min_length = 15, max_length=60):
    tokenizer, model = _get_bart_model()

    inputs = tokenizer(full_text, return_tensors="pt", truncation=True, max_length=1024)
    summary_ids = model.generate(
        inputs["input_ids"],
        max_length=max_length,
        min_length=min_length,
        num_beams=4,
        length_penalty=2.0,
    )
    summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
    return [{"summary_text": summary}]
