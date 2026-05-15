"""Audio download (yt-dlp) + speech-to-text (faster-whisper).

The model is loaded lazily and cached process-wide so repeated
transcription calls don't pay the load cost more than once.

Audio is downloaded as ``bestaudio`` (no post-processing) — that
sidesteps the system ffmpeg dependency. faster-whisper bundles PyAV
to decode the resulting m4a/webm/opus directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yt_dlp
from faster_whisper import WhisperModel

from newsletter.core.config import get_settings
from newsletter.core.logging import get_logger

log = get_logger(__name__)


class STTError(Exception):
    """Raised when audio download or transcription fails."""


@dataclass(slots=True)
class TranscriptionResult:
    audio_path: Path
    transcript_path: Path
    text: str
    language: str
    duration_seconds: float


@lru_cache(maxsize=4)
def _get_whisper_model(model: str, device: str, compute_type: str) -> WhisperModel:
    log.info("whisper.load_model", model=model, device=device, compute_type=compute_type)
    return WhisperModel(model, device=device, compute_type=compute_type)


def download_audio(video_url: str, dest_dir: Path) -> Path:
    """Download the best audio stream for ``video_url`` into ``dest_dir``.

    Returns the path to the downloaded file. Raises :class:`STTError`
    on any yt-dlp failure (private video, network, etc.).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(dest_dir / "%(id)s.%(ext)s")
    options: dict[str, object] = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2,
        "fragment_retries": 2,
        # Don't post-process — that needs ffmpeg. PyAV in faster-whisper
        # will decode whatever container yt-dlp gives us.
        "postprocessors": [],
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(video_url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise STTError(f"yt-dlp download failed for {video_url}: {exc}") from exc

    if not info:
        raise STTError(f"yt-dlp returned no info for {video_url}")

    # yt-dlp picks the actual extension based on the stream; ``ext`` in info
    # is the chosen one.
    video_id = info.get("id")
    ext = info.get("ext")
    if not video_id or not ext:
        raise STTError(f"yt-dlp info missing id/ext for {video_url}: {info!r}")
    path = dest_dir / f"{video_id}.{ext}"
    if not path.exists():
        raise STTError(f"expected downloaded audio at {path}, but file is missing")
    return path


def transcribe(audio_path: Path) -> tuple[str, str, float]:
    """Run faster-whisper on ``audio_path``.

    Returns ``(text, language, duration_seconds)``.
    """
    settings = get_settings()
    model = _get_whisper_model(
        settings.whisper_model, settings.whisper_device, settings.whisper_compute_type
    )
    language = settings.whisper_language or None
    try:
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=5,
            vad_filter=True,
        )
    except Exception as exc:
        raise STTError(f"whisper transcription failed for {audio_path}: {exc}") from exc

    parts = [seg.text.strip() for seg in segments if seg.text]
    text = " ".join(parts).strip()
    return text, info.language or "", float(info.duration or 0.0)


def download_and_transcribe(video_url: str, video_id: str, dest_dir: Path) -> TranscriptionResult:
    """Download audio for ``video_url`` then transcribe it.

    Writes ``<id>.<ext>`` (audio) and ``<id>.txt`` (transcript) inside
    ``dest_dir``.
    """
    audio = download_audio(video_url, dest_dir)
    text, language, duration = transcribe(audio)
    transcript_path = dest_dir / f"{video_id}.txt"
    transcript_path.write_text(text, encoding="utf-8")
    log.info(
        "stt.done",
        video_id=video_id,
        language=language,
        duration_seconds=duration,
        chars=len(text),
    )
    return TranscriptionResult(
        audio_path=audio,
        transcript_path=transcript_path,
        text=text,
        language=language,
        duration_seconds=duration,
    )
