#!/usr/bin/env python3
"""Render QA previews by cropping the exact encoded final pet atlas.

This script never invents, redraws, or modifies pet pixels.  It extracts the
documented final cells, renders the per-state GIFs, and adds
labels outside those pixels for motion proof and still-frame inspection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont


STATES = [
    ("idle", 6, [280, 110, 110, 140, 140, 320]),
    ("running-right", 8, [120] * 7 + [220]),
    ("running-left", 8, [120] * 7 + [220]),
    ("waving", 4, [140, 140, 140, 280]),
    ("jumping", 5, [140, 140, 140, 140, 280]),
    ("failed", 8, [140] * 7 + [240]),
    ("waiting", 6, [150] * 5 + [260]),
    ("running", 6, [120] * 5 + [220]),
    ("review", 6, [150] * 5 + [280]),
]
DEGREES = ["000", "022.5", "045", "067.5", "090", "112.5", "135", "157.5",
           "180", "202.5", "225", "247.5", "270", "292.5", "315", "337.5"]
BG = (245, 247, 250, 255)


def font(size: int = 14):
    for path in ["/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/Library/Fonts/Arial.ttf"]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def cell(atlas: Image.Image, row: int, frame: int) -> Image.Image:
    return atlas.crop((frame * 192, row * 208, (frame + 1) * 192, (row + 1) * 208))


def native_visible(frame: Image.Image) -> Image.Image:
    panel = Image.new("RGBA", (192, 208), BG)
    panel.alpha_composite(frame)
    return panel.convert("RGB")


def labeled(frame: Image.Image, title: str) -> Image.Image:
    panel = Image.new("RGBA", (256, 260), BG)
    panel.alpha_composite(frame, (32, 30))
    draw = ImageDraw.Draw(panel)
    draw.text((12, 8), title, fill=(25, 33, 46), font=font())
    return panel.convert("RGB")


def gif(frames: list[Image.Image], durations: list[int], path: Path):
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations,
                   loop=0, disposal=2, optimize=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    atlas_path = args.atlas.expanduser().resolve()
    out = args.output_dir.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    source_bytes = atlas_path.read_bytes()
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    with Image.open(atlas_path) as opened:
        if opened.size != (1536, 2288):
            raise SystemExit(f"Expected exact v2 atlas 1536x2288, got {opened.size}")
        atlas = opened.convert("RGBA")

    frames_root = out / "final-frames"
    state_frames: dict[str, list[Image.Image]] = {}
    all_frames: list[Image.Image] = []
    all_durations: list[int] = []
    panels_dir = out / "all-state-panels"
    panels_dir.mkdir(exist_ok=True)
    for row, (state, count, durations) in enumerate(STATES):
        dest = frames_root / state
        dest.mkdir(parents=True, exist_ok=True)
        frames = [cell(atlas, row, index) for index in range(count)]
        state_frames[state] = frames
        for index, frame in enumerate(frames):
            frame.save(dest / f"{index:02}.png")
            panel = labeled(frame, f"{state}  {index + 1}/{count}")
            panel.save(panels_dir / f"{len(all_frames):03}.png")
            all_frames.append(panel)
        all_durations.extend(durations)

    (out / "states").mkdir(exist_ok=True)
    for state, _, durations in STATES:
        gif(state_frames[state], durations, out / "states" / f"{state}.gif")
    gif(all_frames, all_durations, out / "all-states.gif")

    # Encode exactly the labeled all-state preview sequence with matching timings.
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required for the MP4 preview")
    concat = panels_dir / "timings.ffconcat"
    lines = ["ffconcat version 1.0"]
    for index, duration in enumerate(all_durations):
        lines += [f"file '{index:03}.png'", f"duration {duration / 1000:.3f}"]
    lines.append(f"file '{len(all_frames) - 1:03}.png'")
    concat.write_text("\n".join(lines) + "\n")
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-safe", "0",
                    "-i", str(concat), "-vf", "fps=30", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    str(out / "all-states.mp4")], check=True)

    transition = (state_frames["idle"] + state_frames["jumping"] + state_frames["idle"])
    transition_durations = STATES[0][2] + STATES[4][2] + STATES[0][2]
    gif([native_visible(frame) for frame in transition], transition_durations,
        out / "idle-jump-idle.gif")

    looks = [cell(atlas, 9 + index // 8, index % 8) for index in range(16)]
    look_dir = frames_root / "look"
    look_dir.mkdir(exist_ok=True)
    for index, frame in enumerate(looks):
        frame.save(look_dir / f"{DEGREES[index]}.png")
    gif([labeled(frame, f"look {DEGREES[index]} deg") for index, frame in enumerate(looks)],
        [180] * 16, out / "look-loop.gif")

    stills_dir = out / "stills"
    stills_dir.mkdir(exist_ok=True)
    picks = [("idle", 0), ("waving", 2), ("jumping", 2), ("failed", 3),
             ("running", 3), ("review", 3)]
    stills = []
    for state, index in picks:
        panel = labeled(state_frames[state][index], f"{state} / frame {index + 1}")
        panel.save(stills_dir / f"{state}-{index + 1:02}.png")
        stills.append(panel)
    for index in [0, 4, 8, 12]:
        panel = labeled(looks[index], f"look {DEGREES[index]} deg")
        panel.save(stills_dir / f"look-{DEGREES[index]}.png")
        stills.append(panel)
    sheet = Image.new("RGB", (256 * 5, 260 * 2), BG[:3])
    for index, panel in enumerate(stills):
        sheet.paste(panel, ((index % 5) * 256, (index // 5) * 260))
    sheet.save(out / "motion-stills.png")

    if hashlib.sha256(atlas_path.read_bytes()).hexdigest() != source_sha:
        raise SystemExit("Source atlas changed during preview rendering")
    manifest = {
        "ok": True,
        "source_atlas": str(atlas_path), "source_sha256": source_sha,
        "source_byte_length": len(source_bytes), "cell_size": [192, 208],
        "frames_root": str(frames_root),
        "per_state_gifs": [str(out / "states" / f"{state}.gif") for state, _, _ in STATES],
        "all_state_gif": str(out / "all-states.gif"),
        "all_state_mp4": str(out / "all-states.mp4"),
        "idle_jump_idle": str(out / "idle-jump-idle.gif"),
        "look_loop": str(out / "look-loop.gif"),
        "labeled_stills": str(out / "motion-stills.png"),
        "standard_frame_count": len(all_frames), "look_frame_count": 16,
        "note": "Previews generated from exact encoded atlas; this is not a visual QA verdict.",
    }
    (out / "preview-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
