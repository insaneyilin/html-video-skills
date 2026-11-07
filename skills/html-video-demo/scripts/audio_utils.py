"""Word alignment, quiet cuts and sample-preserving chapter assembly."""

import math

import numpy as np

from common import normalized


def aligned_cues(lines, items, duration):
    """Map aligner tokens to the original narration lines.

    Args:
        lines: Original caption-sized narration strings.
        items: Objects with text, start_time and end_time.
        duration: Audio duration in seconds.

    Returns:
        Caption intervals and normalized-character-indexed words.

    Raises:
        ValueError: If text differs, timestamps are invalid, or a cue collapses.
    """
    items = list(items)
    if normalized(" ".join(lines)) != normalized("".join(item.text for item in items)):
        raise ValueError("Alignment tokens do not cover the supplied script")
    words, cursor = [], 0
    for item in items:
        token = normalized(item.text)
        if not token:
            continue
        if not (0 <= item.start_time <= item.end_time <= duration + 0.15):
            raise ValueError("Alignment timestamp outside the audio")
        words.append(
            {
                "text": item.text,
                "start": item.start_time,
                "end": min(duration, item.end_time),
                "char_start": cursor,
                "char_end": cursor + len(token),
            }
        )
        cursor += len(token)
    cues, cursor = [], 0
    for line in lines:
        end = cursor + len(normalized(line))
        selected = [
            w for w in words if w["char_end"] > cursor and w["char_start"] < end
        ]
        if not selected or selected[-1]["end"] - selected[0]["start"] < 0.15:
            raise ValueError("Collapsed caption interval; inspect speech and alignment")
        cue = {"text": line, "start": selected[0]["start"], "end": selected[-1]["end"]}
        if cues and cue["start"] < cues[-1]["end"]:
            raise ValueError(
                "Overlapping aligned caption lines; inspect the boundaries"
            )
        cues.append(cue)
        cursor = end
    return cues, words


def quiet_cut(audio, sample_rate, previous_end, following_start, threshold_db=-43):
    """Find a low-energy cut between, never inside, aligned spoken phrases.

    Args:
        audio: Mono samples.
        sample_rate: Samples per second.
        previous_end: Previous phrase's end in seconds.
        following_start: Following phrase's start in seconds.
        threshold_db: Maximum local RMS for a cut.

    Returns:
        Sample index and measured RMS in dBFS.

    Raises:
        ValueError: If there is no safe quiet interval.
    """
    radius = max(1, round(0.01 * sample_rate))
    left = max(radius, round((previous_end + 0.04) * sample_rate))
    right = min(len(audio) - radius, round((following_start - 0.04) * sample_rate))
    if right <= left:
        raise ValueError(
            "No pause between chapters; regroup scenes or regenerate this passage"
        )
    candidates = np.arange(left, right, max(1, round(0.005 * sample_rate)))
    powers = np.array(
        [np.mean(audio[i - radius : i + radius] ** 2) for i in candidates]
    )
    quiet = candidates[powers < 10 ** (threshold_db / 10)]
    if not len(quiet):
        raise ValueError(
            "No sufficiently quiet cut; inspect the audio instead of clipping speech"
        )
    cut = int(quiet[np.argmin(np.abs(quiet - (left + right) / 2))])
    rms = float(
        20
        * np.log10(
            max(np.sqrt(np.mean(audio[cut - radius : cut + radius] ** 2)), 1e-10)
        )
    )
    return cut, rms


def assemble(project, audio, sample_rate, cues, words):
    """Preserve source samples and add configurable visual holds per scene.

    Args:
        project: Validated project configuration.
        audio: Complete normalized narration.
        sample_rate: Samples per second.
        cues: Globally aligned caption intervals.
        words: Aligned words with normalized character offsets.

    Returns:
        Scene timing records, padded chapter arrays and a boundary audit.

    Raises:
        ValueError: If cuts are unsafe, media markers cannot be found, or samples
            are omitted while partitioning.
    """
    groups, cursor, character = [], 0, 0
    for scene in project["scenes"]:
        count = len(scene["narration"])
        length = len(normalized(" ".join(scene["narration"])))
        groups.append((scene, cues[cursor : cursor + count], character))
        cursor += count
        character += length
    if cursor != len(cues):
        raise ValueError("Scene and caption counts disagree")
    cuts, records = [0], []
    settings = project["alignment"]
    for (scene, previous, _), (_, following, _) in zip(groups, groups[1:]):
        cut, rms = quiet_cut(
            audio,
            sample_rate,
            previous[-1]["end"],
            following[0]["start"],
            settings.get("cut_rms_dbfs", -43),
        )
        cuts.append(cut)
        records.append(
            {
                "after": scene["id"],
                "source_cut": cut / sample_rate,
                "last_word_end": previous[-1]["end"],
                "next_word_start": following[0]["start"],
                "rms_dbfs": rms,
            }
        )
    cuts.append(len(audio))
    pieces = [audio[a:b] for a, b in zip(cuts, cuts[1:])]
    if not np.array_equal(np.concatenate(pieces), audio):
        raise ValueError("Audio samples were omitted or changed during splitting")
    pre, hold, fps = (
        settings["pre_roll_seconds"],
        settings["end_hold_seconds"],
        project["video"]["fps"],
    )
    scenes, padded, position = [], [], 0
    for i, (scene, original, character) in enumerate(groups):
        origin = cuts[i] / sample_rate
        local = [
            {
                "text": c["text"],
                "start": round(pre + c["start"] - origin, 3),
                "end": round(pre + c["end"] - origin + 0.08, 3),
            }
            for c in original
        ]
        for j in range(len(local) - 1):
            local[j]["end"] = min(local[j]["end"], local[j + 1]["start"])
        marks = {}
        text = normalized(" ".join(scene["narration"]))
        for key, phrase in scene.get("markers", {}).items():
            found = text.find(normalized(phrase))
            if found < 0:
                raise ValueError(f"Marker {key} does not occur in scene {scene['id']}")
            word = next(w for w in words if w["char_end"] > character + found)
            marks[key] = round(pre + word["start"] - origin, 3)
        media_end = 0
        if scene.get("kind") == "video":
            media_start = marks.get("video", scene.get("media_start", 0.8))
            marks["video"] = media_start
            media_end = media_start + scene["media_duration"] + 0.25
        duration = (
            math.ceil(
                max(
                    pre + len(pieces[i]) / sample_rate + 0.2,
                    local[-1]["end"] + hold,
                    media_end,
                )
                * fps
            )
            / fps
        )
        data = np.zeros(round(duration * sample_rate), dtype=np.float32)
        offset = round(pre * sample_rate)
        data[offset : offset + len(pieces[i])] = pieces[i]
        padded.append(data)
        scenes.append(
            {
                **scene,
                "cues": local,
                "marks": marks,
                "duration": duration,
                "start": position,
                "end_hold": round(duration - local[-1]["end"], 3),
            }
        )
        position += duration
    return (
        scenes,
        padded,
        {
            "samples_preserved": True,
            "cuts": records,
            "minimum_end_hold": min(s["end_hold"] for s in scenes),
        },
    )
