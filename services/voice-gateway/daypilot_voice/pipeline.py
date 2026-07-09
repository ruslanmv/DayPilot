from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import FastAPI
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from starlette.responses import Response

VOICE_SESSIONS = Counter("daypilot_voice_sessions_total", "Voice pipeline sessions")
TRANSCRIPTS = Counter("daypilot_voice_transcripts_total", "Transcription requests")


@dataclass
class VoiceStage:
    name: str
    backend: str
    state: str = "ready"


class TranscribeRequest(BaseModel):
    audio_ref: str
    language: str = "en"


class SpeakRequest(BaseModel):
    text: str
    voice: str = "daypilot-default"


def describe_voice_pipeline() -> list[str]:
    return [
        "SIP/WebRTC ingress",
        "Voice activity detection",
        f"Streaming ASR ({os.getenv('DAYPILOT_ASR_BACKEND', 'mock')})",
        "Governed Agent Runtime",
        f"Streaming TTS ({os.getenv('DAYPILOT_TTS_BACKEND', 'mock')})",
        "Operator takeover and audit trail",
    ]


def transcribe(audio_ref: str, language: str = "en") -> dict:
    TRANSCRIPTS.inc()
    return {
        "status": "mock_transcribed",
        "audio_ref": audio_ref,
        "language": language,
        "text": "Voice gateway placeholder transcript. Configure ASR backend for real audio.",
    }


def synthesize(text: str, voice: str = "daypilot-default") -> dict:
    VOICE_SESSIONS.inc()
    return {"status": "mock_synthesized", "voice": voice, "audio_ref": "memory://mock-tts.wav", "text": text}


app = FastAPI(title="DayPilot Voice Gateway", version="0.2.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "daypilot-voice-gateway", "pipeline": describe_voice_pipeline()}


@app.get("/v1/pipeline")
def pipeline() -> dict:
    return {"stages": describe_voice_pipeline()}


@app.post("/v1/transcribe")
def transcribe_endpoint(request: TranscribeRequest) -> dict:
    return transcribe(request.audio_ref, request.language)


@app.post("/v1/speak")
def speak_endpoint(request: SpeakRequest) -> dict:
    return synthesize(request.text, request.voice)


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
