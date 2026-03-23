import os
import warnings
import nltk
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from textsplit.tools import get_penalty, get_segments
from textsplit.algorithm import split_optimal
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

    # Use textsplit's optimal segmentation algorithm to find topic boundaries.
    # It uses dynamic programming to maximize segment coherence given a penalty
    # that controls granularity. Aim for ~8-12 broad topics.
    target_segments = min(12, max(2, len(sentences) // 200))
    avg_segment_len = len(sentences) // target_segments
    penalty = get_penalty([embeddings], avg_segment_len)
    optimal_splits = split_optimal(embeddings, penalty)
    segment_groups = get_segments(sentences, optimal_splits)

    # Convert textsplit output to boundary indices
    boundaries = [0]
    pos = 0
    for group in segment_groups:
        pos += len(group)
        boundaries.append(pos)

    # Group up boundaries into a list of segments with text and start time for each
    segments_boundaries = zip(boundaries, boundaries[1:])
    results = []
    for start, end in segments_boundaries:
        results.append({
            "text": " ".join(sentences[start:end]),
            "start_time": int(sentence_timestamps[start]) if sentence_timestamps[start] is not None else None,
        })
    return results

# -- BART summarization (commented out for Qwen2 experiment) --
# _bart_tokenizer = None
# _bart_model = None
#
# def _get_bart_model():
#     from transformers import BartTokenizer, BartForConditionalGeneration
#     global _bart_tokenizer, _bart_model
#     if _bart_tokenizer is None:
#         _bart_tokenizer = BartTokenizer.from_pretrained("philschmid/bart-large-cnn-samsum")
#         _bart_model = BartForConditionalGeneration.from_pretrained("philschmid/bart-large-cnn-samsum")
#     assert _bart_tokenizer is not None and _bart_model is not None
#     return _bart_tokenizer, _bart_model

_summary_pipe = None

def _get_summary_pipe():
    """Lazy-load the Qwen2 LLM pipeline for summarization (shared with chatbot)."""
    global _summary_pipe
    if _summary_pipe is None:
        from chatbot import LLM_MODEL
        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch

        tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            LLM_MODEL,
            torch_dtype=torch.float32,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        ).to("cpu")

        _summary_pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
        )
    return _summary_pipe

SUMMARY_PROMPT = """Summarize the following podcast transcript in {style}. Only output the summary, nothing else.

Transcript:
---
{text}
---

Summary:"""

TITLE_PROMPT = """What is the main topic of this podcast excerpt? Respond with only a short title (3-7 words). Do not use quotes or punctuation.

Excerpt:
---
{text}
---

Title:"""

def generate_topic_title(text: str) -> str:
    """Generates a short topic title for a text segment using the LLM."""
    pipe = _get_summary_pipe()
    # Use first 2000 chars — enough context for a title
    truncated = text[:2000]
    prompt = TITLE_PROMPT.format(text=truncated)
    messages = [{"role": "user", "content": prompt}]

    outputs = pipe(
        messages,
        max_new_tokens=20,
        max_length=None,
        temperature=0.3,
        top_p=0.9,
        do_sample=True,
        pad_token_id=pipe.tokenizer.eos_token_id,
        return_full_text=False,
    )

    raw = outputs[0] if isinstance(outputs, list) else outputs
    response = raw["generated_text"]
    if isinstance(response, list):
        response = response[-1].get("content", str(response))

    return response.strip().strip('"').strip("'")

BLOCK_SIZE = 12000

def _generate_summary(pipe, text: str, style: str, max_tokens: int) -> str:
    """Run a single summarization prompt through the LLM pipeline."""
    prompt = SUMMARY_PROMPT.format(style=style, text=text)
    messages = [{"role": "user", "content": prompt}]

    outputs = pipe(
        messages,
        max_new_tokens=max_tokens,
        max_length=None,
        temperature=0.3,
        top_p=0.9,
        do_sample=True,
        pad_token_id=pipe.tokenizer.eos_token_id,
        return_full_text=False,
    )

    raw = outputs[0] if isinstance(outputs, list) else outputs
    response = raw["generated_text"]
    if isinstance(response, list):
        response = response[-1].get("content", str(response))

    return response.strip()

def summarize_text(full_text: str, min_length=15, max_length=60):
    pipe = _get_summary_pipe()

    # Choose style based on requested length
    if max_length <= 120:
        style = "1-2 concise sentences"
    else:
        style = "a concise summary of 8-12 sentences. Do not exceed 12 sentences"

    # Break input into blocks and summarize each one
    blocks = [full_text[i:i + BLOCK_SIZE] for i in range(0, len(full_text), BLOCK_SIZE)]

    if len(blocks) == 1:
        # Short text, summarize directly
        summary = _generate_summary(pipe, blocks[0], style, max_tokens=max_length)
    else:
        # Summarize each block individually
        block_summaries = []
        for i, block in enumerate(blocks):
            block_summary = _generate_summary(pipe, block, "a short paragraph (3-5 sentences)", max_tokens=200)
            block_summaries.append(block_summary)

        # Combine block summaries and produce a final summary
        combined = "\n".join(block_summaries)
        result = summarize_text(combined, min_length=min_length, max_length=max_length)
        summary = result[0]["summary_text"]

    return [{"summary_text": summary}]
