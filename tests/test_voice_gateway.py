from daypilot_voice.pipeline import describe_voice_pipeline, synthesize, transcribe


def test_voice_pipeline_mock_contracts():
    stages = describe_voice_pipeline()
    assert any("ASR" in stage for stage in stages)
    assert transcribe("memory://audio.wav")["status"] == "mock_transcribed"
    assert synthesize("hello")["status"] == "mock_synthesized"
