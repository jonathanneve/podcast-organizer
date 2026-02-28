import os
from pyannote.audio import Pipeline

def diarize_audio_file(path):
    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        raise ValueError("HF_TOKEN environment variable not set")

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-community-1",
        use_auth_token=hf_token
    )

    # run the pipeline on an audio file
    output = pipeline(path)

    # dump the diarization output to disk using RTTM format
    # with open("audio.rttm", "w") as rttm:
    #     diarization.write_rttm(rttm)

    # from pyannote.audio import Pipeline
    # pipeline = Pipeline.from_pretrained('pyannote/speaker-diarization-community-1', token="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")

    # # perform speaker diarization locally
    # output = pipeline('/path/to/audio.wav')

    # enjoy state-of-the-art speaker diarization
    for turn, speaker in output.speaker_diarization:
        print(f"{speaker} speaks between t={turn.start}s and t={turn.end}s")