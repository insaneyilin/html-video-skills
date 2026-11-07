"""Configurable local narration workflow for html-video projects."""

import argparse
import difflib
import gc
import importlib.metadata
import json
import time
from pathlib import Path

from common import (
    fingerprint,
    init_project,
    inside,
    load_project,
    normalized,
    plan_groups,
    read_json,
    run,
    source_signature,
    subtitle_time,
    write_json,
)


def model_path(model, revision):
    """Resolve pinned public weights from the normal local model cache.

    Args:
        model: Hugging Face repository ID.
        revision: Explicit model commit or tag.

    Returns:
        Path to the cached snapshot.
    """
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            model,
            revision=revision,
            token=False,
            max_workers=2,
            allow_patterns=["*.json", "*.txt", "*.safetensors", "speech_tokenizer/*"],
        )
    )


def generate(model, text, settings, audit):
    """Generate one bounded, unpadded preset-voice utterance.

    Args:
        model: Loaded CustomVoice model with configured decoder policy.
        text: Continuous spoken passage.
        settings: Voice and sampling configuration.
        audit: Decoder diagnostics shared with the model adapter.

    Returns:
        Audio array, sample rate and generation statistics.

    Raises:
        RuntimeError: If generation is empty, truncated or non-finite.
    """
    import mlx.core as mx
    import numpy as np

    mx.random.seed(settings["seed"])
    mx.reset_peak_memory()
    started = time.perf_counter()
    before = len(audit)
    results = list(
        model.generate_custom_voice(
            text=text,
            speaker=settings["speaker"],
            language=settings["language"],
            instruct=settings["instruction"],
            temperature=settings["temperature"],
            max_tokens=settings["max_tokens"],
            stream=False,
            verbose=False,
        )
    )
    if not results or any(r.token_count >= settings["max_tokens"] for r in results):
        raise RuntimeError(
            "Speech reached its token cap or was empty; shorten this group rather than exporting it"
        )
    audio = np.concatenate(
        [np.asarray(r.audio, dtype=np.float32).reshape(-1) for r in results]
    )
    sr = results[0].sample_rate
    if len(audio) < sr or not np.isfinite(audio).all():
        raise RuntimeError("Invalid speech samples")
    result = {
        "duration": len(audio) / sr,
        "sample_rate": sr,
        "generation_seconds": time.perf_counter() - started,
        "tokens": sum(r.token_count for r in results),
        "peak_memory_gb": mx.get_peak_memory() / 1e9,
        "decode": audit[before:],
    }
    mx.clear_cache()
    return audio, sr, result


def load_voice(project):
    """Load the selected voice and probe the known decoder-length invariant.

    Args:
        project: Project configuration.

    Returns:
        Model and mutable decoder audit list.
    """
    import mlx.core as mx
    from mlx_audio.tts.utils import load_model
    from qwen_decode import configure_decoder

    if not mx.metal.is_available():
        raise RuntimeError("Included TTS helper requires Apple Silicon and Metal")
    v = project["voice"]
    model = load_model(model_path(v["model"], v["revision"]))
    audit = []
    configure_decoder(model.speech_tokenizer, audit, v.get("decoder_policy", "auto"))
    print(json.dumps({"decoder_probe": audit[0]}, ensure_ascii=False), flush=True)
    return model, audit


def synthesize(root, project):
    """Generate semantic groups, resuming only matching successful cache entries.

    Args:
        root: Project directory.
        project: Validated manifest.
    """
    import numpy as np
    import soundfile as sf

    settings = {**project["voice"], "language": project["language"]}
    versions = {k: importlib.metadata.version(k) for k in ["mlx", "mlx-audio"]}
    groups = plan_groups(project)
    lookup = {s["id"]: s for s in project["scenes"]}
    folder = root / "work/groups"
    folder.mkdir(parents=True, exist_ok=True)
    model, audit, pieces, records, sr = None, [], [], [], None
    for i, ids in enumerate(groups):
        text = "\n\n".join(" ".join(lookup[key]["narration"]) for key in ids)
        signature = fingerprint(
            {"settings": settings, "text": text, "runtime": versions, "pipeline": 1}
        )
        base = folder / f"group-{i + 1}"
        metadata = base.with_suffix(".json")
        wave = base.with_suffix(".wav")
        if (
            metadata.exists()
            and wave.exists()
            and read_json(metadata).get("signature") == signature
        ):
            audio, sample_rate = sf.read(wave, dtype="float32")
            record = read_json(metadata)
            print(f"Reuse group {i + 1}/{len(groups)}", flush=True)
        else:
            if model is None:
                model, audit = load_voice(project)
            print(f"Generate group {i + 1}/{len(groups)}: {', '.join(ids)}", flush=True)
            audio, sample_rate, record = generate(model, text, settings, audit)
            temporary = folder / f"group-{i + 1}.pending.wav"
            sf.write(temporary, audio, sample_rate, subtype="FLOAT")
            temporary.replace(wave)
            record.update(
                {
                    "signature": signature,
                    "text": text,
                    "scenes": ids,
                    "file": str(wave.relative_to(root)),
                    "runtime": versions,
                }
            )
            write_json(metadata, record)
        if sr is not None and sr != sample_rate:
            raise RuntimeError("Generated sample rates disagree")
        sr = sample_rate
        if pieces:
            pieces.append(np.zeros(round(0.7 * sr), dtype=np.float32))
        pieces.append(audio)
        records.append(record)
    master = root / "work/narration-raw.wav"
    sf.write(master, np.concatenate(pieces), sr, subtype="FLOAT")
    write_json(
        root / "work/synthesis.json",
        {
            "source_signature": source_signature(root),
            "groups": records,
            "voice": settings["speaker"],
            "model": settings["model"],
            "decoder_audit": audit,
        },
    )
    print(
        "Narration generated; review audio and run check-text before final export.",
        flush=True,
    )


def audition(root, project, speakers, text):
    """Create same-text, equal-loudness preset voice samples.

    Args:
        root: Project directory.
        project: Validated manifest.
        speakers: Preset voice names to compare.
        text: Shared audition passage.
    """
    import soundfile as sf

    folder = root / "work/auditions" / str(time.time_ns())
    folder.mkdir(parents=True)
    model, audit = load_voice(project)
    rows = []
    for speaker in speakers:
        settings = {
            **project["voice"],
            "language": project["language"],
            "speaker": speaker,
        }
        audio, sr, stats = generate(model, text, settings, audit)
        raw = folder / (speaker + "-raw.wav")
        sf.write(raw, audio, sr, subtype="FLOAT")
        target = folder / (speaker + ".wav")
        normalize_audio(raw, target, settings["target_lufs"])
        rows.append(
            {"speaker": speaker, "file": str(target.relative_to(root)), **stats}
        )
    write_json(folder / "auditions.json", {"text": text, "samples": rows})
    print(str(folder))


def normalize_audio(source, target, lufs):
    """Normalize the full soundtrack once, without time stretching.

    Args:
        source: Input audio file.
        target: Output mono PCM WAV file.
        lufs: Integrated loudness target.
    """
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            source,
            "-af",
            f"loudnorm=I={lufs}:TP=-2:LRA=9",
            "-ar",
            "48000",
            "-ac",
            "1",
            target,
        ]
    )


def require_current(root, project, filename):
    """Reject stale intermediate results from an earlier manifest.

    Args:
        root: Project directory.
        project: Current manifest.
        filename: Work file to inspect.

    Returns:
        Intermediate result with matching source identity.

    Raises:
        ValueError: If the manifest changed since this result was produced.
    """
    data = read_json(root / "work" / filename)
    if data.get("source_signature") != source_signature(root):
        raise ValueError(f"{filename} is stale; rerun the preceding stage")
    return data


def check_text(root, project):
    """Use independent ASR to surface omissions and transcription differences.

    Args:
        root: Project directory.
        project: Current manifest.
    """
    from mlx_audio.stt import load

    data = require_current(root, project, "synthesis.json")
    a = project["alignment"]
    model = load(model_path(a["asr_model"], a["asr_revision"]))
    checks = []
    for group in data["groups"]:
        heard = model.generate(
            str(inside(root, group["file"])), language=project["language"]
        ).text
        expected, actual = normalized(group["text"]), normalized(heard)
        match = difflib.SequenceMatcher(a=expected, b=actual, autojunk=False)
        differences = [
            {"expected": expected[i:j], "heard": actual[k:l]}
            for tag, i, j, k, l in match.get_opcodes()
            if tag != "equal"
        ]
        item = {
            "scenes": group["scenes"],
            "expected": group["text"],
            "transcript": heard,
            "similarity": match.ratio(),
            "differences": differences,
        }
        checks.append(item)
        print(json.dumps(item, ensure_ascii=False), flush=True)
    write_json(
        root / "work/transcript-check.json",
        {
            "source_signature": source_signature(root),
            "checks": checks,
            "review_needed": any(c["differences"] for c in checks),
        },
    )


def align(root, project):
    """Align narration and assemble captions, safe scene cuts and holds.

    Args:
        root: Project directory.
        project: Current manifest.
    """
    import numpy as np
    import soundfile as sf
    import mlx.core as mx
    from mlx_audio.stt import load
    from audio_utils import aligned_cues, assemble

    require_current(root, project, "synthesis.json")
    normalized_path = root / "work/narration-normalized.wav"
    normalize_audio(
        root / "work/narration-raw.wav",
        normalized_path,
        project["voice"]["target_lufs"],
    )
    waveform, sr = sf.read(normalized_path, dtype="float32")
    settings = project["alignment"]
    model = load(model_path(settings["model"], settings["revision"]))
    lines = [line for scene in project["scenes"] for line in scene["narration"]]
    result = model.generate(
        audio=str(normalized_path), text=" ".join(lines), language=project["language"]
    )
    cues, words = aligned_cues(lines, result, len(waveform) / sr)
    del model
    gc.collect()
    mx.clear_cache()
    write_json(root / "work/word-alignment.json", {"cues": cues, "words": words})
    for scene in project["scenes"]:
        if scene.get("kind") == "video":
            scene["media_duration"] = float(
                run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=nw=1:nk=1",
                        inside(root, scene["media"]),
                    ]
                ).strip()
            )
    scenes, chapters, audit = assemble(project, waveform, sr, cues, words)
    folder = root / "work/chapters"
    folder.mkdir(exist_ok=True)
    for scene, chapter in zip(scenes, chapters):
        sf.write(folder / (scene["id"] + ".wav"), chapter, sr, subtype="PCM_16")
    sf.write(
        root / "work/narration.wav", np.concatenate(chapters), sr, subtype="PCM_16"
    )
    # Derived media duration is not part of the editable manifest identity.
    signature = source_signature(root)
    timing = {
        "source_signature": signature,
        "title": project["title"],
        "video": project["video"],
        "voice": project["voice"]["speaker"],
        "scenes": scenes,
        "duration": sum(s["duration"] for s in scenes),
        "narration": "work/narration.wav",
    }
    write_json(root / "work/timing.json", timing)
    write_json(root / "work/boundaries.json", audit)
    global_cues = [
        {**c, "start": c["start"] + s["start"], "end": c["end"] + s["start"]}
        for s in scenes
        for c in s["cues"]
    ]
    for ext, separator, prefix in [("srt", ",", ""), ("vtt", ".", "WEBVTT\n\n")]:
        text = (
            prefix
            + "\n\n".join(
                f"{i + 1}\n{subtitle_time(c['start'], separator)} --> {subtitle_time(c['end'], separator)}\n{c['text']}"
                for i, c in enumerate(global_cues)
            )
            + "\n"
        )
        (root / "work" / ("subtitles." + ext)).write_text(text, encoding="utf-8")
    print(
        f"Aligned {len(scenes)} scenes, {timing['duration']:.2f}s; every source sample retained."
    )


def main():
    """Dispatch project creation, narration, alignment and transcript checks."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["init", "validate", "audition", "synthesize", "check-text", "align"],
    )
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--voices", nargs="+")
    parser.add_argument("--text")
    args = parser.parse_args()
    root = args.project.resolve()
    if args.command == "init":
        init_project(root)
        print(f"Created project: {root}")
        return
    project = load_project(root)
    if args.command == "validate":
        print(
            json.dumps(
                {"valid": True, "groups": plan_groups(project)}, ensure_ascii=False
            )
        )
    elif args.command == "audition":
        text = args.text or " ".join(project["scenes"][0]["narration"])
        audition(root, project, args.voices or [project["voice"]["speaker"]], text)
    else:
        {"synthesize": synthesize, "check-text": check_text, "align": align}[
            args.command
        ](root, project)


if __name__ == "__main__":
    main()
