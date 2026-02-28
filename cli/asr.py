import os
import warnings
import subprocess
import tempfile

# Fix OpenMP library conflict on macOS
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Suppress urllib3 OpenSSL warning (LibreSSL vs OpenSSL on macOS)
warnings.filterwarnings("ignore", message=".*urllib3.*")

from faster_whisper import WhisperModel


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
