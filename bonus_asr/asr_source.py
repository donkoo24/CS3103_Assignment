#!/usr/bin/env python3
"""Streaming ASR caption source for LiveRecall (Bonus Feature).

Feeds live or continuous-playback speech recognition updates to solution_server.py
using the exact required LiveRecall protocol:
  - SOURCE_HELLO handshake
  - CAPTION_UPDATE events with provisional (final=false) and finalized (final=true) semantics
  - Monotonically increasing segments and revisions
  - Real-time pacing synchronized with audio playback

Usage examples:
  # Stream 3-minute WAV lecture audio in real time:
  python bonus_asr/asr_source.py --audio bonus_asr/lecture_3min.wav

  # Stream at 2x speed for rapid testing:
  python bonus_asr/asr_source.py --audio bonus_asr/lecture_3min.wav --speed 2.0

  # Stream audio extracted from a lecture video via ffmpeg:
  python bonus_asr/asr_source.py --video path/to/lecture.mp4

  # Use Vosk engine explicitly:
  python bonus_asr/asr_source.py --engine vosk --audio bonus_asr/lecture_3min.wav
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import wave
from pathlib import Path

import websockets

from asr_engine import BaseASREngine, get_asr_engine


def parse_args():
    parser = argparse.ArgumentParser(
        description="LiveRecall Real-Lecture ASR Caption Source"
    )
    parser.add_argument(
        "--uri",
        default="ws://127.0.0.1:8765",
        help="WebSocket URI of LiveRecall server (default: ws://127.0.0.1:8765)",
    )
    parser.add_argument(
        "--session",
        default="L1",
        help="Session identifier (default: L1)",
    )
    default_video = Path(__file__).parent / "my_lecture.mp4"
    parser.add_argument(
        "--video",
        default=str(default_video) if default_video.exists() else None,
        help="Path to video file (if provided, invokes ffmpeg to stream real-time audio)",
    )
    parser.add_argument(
        "--audio",
        default=None,
        help="Path to 16kHz mono WAV audio file, or '-' for raw PCM on stdin",
    )
    parser.add_argument(
        "--engine",
        choices=["auto", "vosk", "faster-whisper", "energy-vad"],
        default="auto",
        help="ASR backend engine (default: auto)",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="Path to local ASR model weights",
    )
    parser.add_argument(
        "--transcript",
        default=str(Path(__file__).parent / "lecture_3min.txt"),
        help="Path to companion lecture transcript (for energy-vad engine)",
    )
    parser.add_argument(
        "--chunk-ms",
        type=int,
        default=200,
        help="Audio chunk duration in milliseconds (default: 200 ms)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Playback speed multiplier (1.0 = real-time, 2.0 = 2x speed)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress printing emitted caption events",
    )
    return parser.parse_args()


class AudioStreamReader:
    """Streams 16kHz 16-bit Mono PCM audio chunks at paced real-time intervals."""

    def __init__(
        self,
        audio_path: str,
        video_path: str | None,
        chunk_ms: int = 200,
        sample_rate: int = 16000,
    ):
        self.chunk_ms = chunk_ms
        self.sample_rate = sample_rate
        self.bytes_per_sample = 2  # 16-bit PCM
        self.chunk_bytes = int((chunk_ms / 1000.0) * sample_rate * self.bytes_per_sample)
        self.ffmpeg_proc: subprocess.Popen | None = None
        self.wav_file: wave.Wave_read | None = None
        self.stdin_mode = False

        if video_path:
            # Find ffmpeg binary (system PATH, venv bin, or imageio_ffmpeg)
            import shutil
            ffmpeg_bin = shutil.which("ffmpeg")
            if not ffmpeg_bin:
                venv_ffmpeg = Path(__file__).parent / ".venv-asr" / "bin" / "ffmpeg"
                if venv_ffmpeg.exists():
                    ffmpeg_bin = str(venv_ffmpeg)
                else:
                    try:
                        import imageio_ffmpeg
                        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
                    except ImportError:
                        pass

            if not ffmpeg_bin:
                sys.exit(
                    "Error: ffmpeg is required when using --video. "
                    "Install via `bonus_asr/.venv-asr/bin/pip install imageio-ffmpeg` or use --audio <file.wav>."
                )

            # Extract and stream audio from video (Python paces chunks to real time)
            cmd = [
                ffmpeg_bin,
                "-i",
                video_path,
                "-vn",  # No video
                "-acodec",
                "pcm_s16le",
                "-ar",
                str(sample_rate),
                "-ac",
                "1",
                "-f",
                "s16le",
                "-",
            ]
            self.ffmpeg_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
        elif audio_path == "-":
            self.stdin_mode = True
        elif audio_path:
            # Read standard WAV file
            path = Path(audio_path)
            if not path.exists():
                sys.exit(f"Error: audio file not found: {audio_path}")
            self.wav_file = wave.open(str(path), "rb")
            if self.wav_file.getnchannels() != 1 or self.wav_file.getsampwidth() != 2:
                print(
                    f"Warning: WAV is {self.wav_file.getnchannels()} channels, "
                    f"{self.wav_file.getsampwidth()} bytes/sample. "
                    f"Recommended: 1 channel, 16-bit PCM."
                )
        else:
            sys.exit("Error: Please provide a media source with --video <file.mp4> or --audio <file.wav>")

    def read_chunk(self) -> bytes:
        if self.ffmpeg_proc:
            return self.ffmpeg_proc.stdout.read(self.chunk_bytes)
        elif self.stdin_mode:
            return sys.stdin.buffer.read(self.chunk_bytes)
        elif self.wav_file:
            frames = self.wav_file.readframes(self.chunk_bytes // self.bytes_per_sample)
            return frames
        return b""

    def close(self):
        if self.wav_file:
            self.wav_file.close()
        if self.ffmpeg_proc:
            self.ffmpeg_proc.terminate()
            self.ffmpeg_proc.wait()


async def stream_captions(args, engine: BaseASREngine) -> None:
    reader = AudioStreamReader(
        audio_path=args.audio,
        video_path=args.video,
        chunk_ms=args.chunk_ms,
    )

    chunk_duration_sec = args.chunk_ms / 1000.0
    sleep_interval = chunk_duration_sec / max(0.1, args.speed)

    current_segment = 1
    current_revision = 0
    last_emitted_text = ""
    start_mono = time.monotonic()
    chunks_processed = 0

    print(
        f"Connecting to LiveRecall server at {args.uri} (session='{args.session}', speed={args.speed}x)...",
        flush=True,
    )

    try:
        async with websockets.connect(args.uri, max_size=2**20) as ws:
            # Send SOURCE_HELLO handshake
            hello_msg = {"type": "SOURCE_HELLO", "session": args.session}
            await ws.send(json.dumps(hello_msg))
            print(f"Connected! Sent SOURCE_HELLO for session {args.session}.", flush=True)

            while True:
                chunk = reader.read_chunk()
                if not chunk:
                    # Stream finished
                    break

                chunks_processed += 1
                result = engine.process_chunk(chunk)

                if result and result.text:
                    if not result.is_final:
                        # Provisional revision: must be non-empty and distinct
                        if result.text != last_emitted_text:
                            current_revision += 1
                            last_emitted_text = result.text
                            event = {
                                "type": "CAPTION_UPDATE",
                                "session": args.session,
                                "segment": current_segment,
                                "revision": current_revision,
                                "source_ts": time.time(),
                                "final": False,
                                "text": result.text,
                            }
                            await ws.send(json.dumps(event))
                            if not args.quiet:
                                print(
                                    f"[Seg {current_segment:02d} | Rev {current_revision:02d} | PROVISIONAL] {result.text}",
                                    flush=True,
                                )
                    else:
                        # Finalized segment: commits durable caption
                        current_revision += 1
                        event = {
                            "type": "CAPTION_UPDATE",
                            "session": args.session,
                            "segment": current_segment,
                            "revision": current_revision,
                            "source_ts": time.time(),
                            "final": True,
                            "text": result.text,
                        }
                        await ws.send(json.dumps(event))
                        if not args.quiet:
                            print(
                                f"[Seg {current_segment:02d} | Rev {current_revision:02d} | FINAL]       {result.text}",
                                flush=True,
                            )
                        # Advance to next segment
                        current_segment += 1
                        current_revision = 0
                        last_emitted_text = ""

                # Real-time pacing
                elapsed = time.monotonic() - start_mono
                expected = chunks_processed * sleep_interval
                delay = expected - elapsed
                if delay > 0:
                    await asyncio.sleep(delay)

            # Flush any remaining buffer at end of audio
            final_res = engine.finish()
            if final_res and final_res.text:
                current_revision += 1
                event = {
                    "type": "CAPTION_UPDATE",
                    "session": args.session,
                    "segment": current_segment,
                    "revision": current_revision,
                    "source_ts": time.time(),
                    "final": True,
                    "text": final_res.text,
                }
                await ws.send(json.dumps(event))
                if not args.quiet:
                    print(
                        f"[Seg {current_segment:02d} | Rev {current_revision:02d} | FINAL-FLUSH] {final_res.text}",
                        flush=True,
                    )

            # End of source stream
            done_msg = {"type": "SOURCE_DONE", "session": args.session}
            await ws.send(json.dumps(done_msg))
            print("Stream completed. Sent SOURCE_DONE.", flush=True)

    finally:
        reader.close()
        engine.close()


def main():
    args = parse_args()
    engine = get_asr_engine(
        backend=args.engine,
        model_path=args.model_path,
        transcript_path=args.transcript,
    )
    print(f"Initialized ASR engine: {engine.__class__.__name__}", flush=True)

    try:
        asyncio.run(stream_captions(args, engine))
    except KeyboardInterrupt:
        print("\nStreaming aborted by user.")
    except Exception as e:
        sys.exit(f"ASR Source error: {e}")


if __name__ == "__main__":
    main()

