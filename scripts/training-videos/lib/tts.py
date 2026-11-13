"""Batch voice-over with Kokoro (open-source, runs offline, no API key, no cost).

stdin: JSON {"voice": "af_heart", "speed": 1.0, "items": [{"text": ..., "out": ...}]}
stdout: JSON list of durations in seconds, same order. A clip already on disk is reused.
Model files: $TV_TTS_DIR (default ~/tts) holds kokoro-v1.0.onnx + voices-v1.0.bin.
"""
import json, os, sys
import soundfile as sf

req = json.load(sys.stdin)
d = os.environ.get("TV_TTS_DIR", os.path.expanduser("~/tts"))
k = None
durs = []
for it in req["items"]:
    if not os.path.exists(it["out"]):
        if k is None:
            from kokoro_onnx import Kokoro
            k = Kokoro(os.path.join(d, "kokoro-v1.0.onnx"), os.path.join(d, "voices-v1.0.bin"))
        v = req.get("voice", "af_heart")
        s, sr = k.create(it["text"], voice=v, speed=req.get("speed", 1.0),
                         lang="en-us" if v[0] == "a" else "en-gb")
        sf.write(it["out"], s, sr)
    info = sf.info(it["out"])
    durs.append(info.frames / info.samplerate)
print(json.dumps(durs))
