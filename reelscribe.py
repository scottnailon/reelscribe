#!/usr/bin/env python3
"""
reelscribe - one command: video URL in, transcript + on-screen text + summary out.

Pipeline:
  1. download  (yt-dlp)      -> media file
  2. transcribe (faster-whisper) -> spoken words
  3. ocr        (ffmpeg frames + tesseract) -> on-screen / burned-in text
  4. summarise  (local Ollama, optional) -> short summary
  5. report     -> combined Markdown file

Designed to run identically on macOS (native) and inside the container.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


def log(msg):
    print(f"[reelscribe] {msg}", file=sys.stderr, flush=True)


def run(cmd):
    """Run a shell command, raising on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout


# ---------------------------------------------------------------- download

def download(url, workdir, cookies_browser=None, cookies_file=None):
    out_tmpl = str(workdir / "source.%(ext)s")
    cmd = ["yt-dlp", "-o", out_tmpl, "--no-playlist", "--quiet", "--no-warnings"]
    if cookies_browser:
        cmd += ["--cookies-from-browser", cookies_browser]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    cmd.append(url)
    log("downloading...")
    run(cmd)
    files = list(workdir.glob("source.*"))
    if not files:
        raise RuntimeError("download produced no file (private reel? try --cookies)")
    return files[0]


# ---------------------------------------------------------------- transcribe

def transcribe(media, model_size, language=None):
    from faster_whisper import WhisperModel

    log(f"transcribing with model '{model_size}' (first run downloads the model)...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(media), beam_size=5, language=language)
    lines, full = [], []
    for seg in segments:
        stamp = f"[{_ts(seg.start)} -> {_ts(seg.end)}]"
        text = seg.text.strip()
        lines.append(f"{stamp} {text}")
        full.append(text)
    return " ".join(full).strip(), "\n".join(lines), info.language


def _ts(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


# ---------------------------------------------------------------- ocr

def ocr(media, workdir, every_seconds=2):
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        log("OCR dependencies missing, skipping on-screen text")
        return ""
    if shutil.which("tesseract") is None:
        log("tesseract not installed, skipping on-screen text")
        return ""

    frames_dir = workdir / "frames"
    frames_dir.mkdir(exist_ok=True)
    log("extracting frames for OCR...")
    run([
        "ffmpeg", "-loglevel", "error", "-i", str(media),
        "-vf", f"fps=1/{every_seconds}",
        str(frames_dir / "f_%05d.png"),
    ])

    seen, ordered = set(), []
    for frame in sorted(frames_dir.glob("f_*.png")):
        raw = pytesseract.image_to_string(Image.open(frame))
        for line in raw.splitlines():
            norm = re.sub(r"\s+", " ", line).strip()
            if len(norm) < 3:
                continue
            key = norm.lower()
            if key not in seen:
                seen.add(key)
                ordered.append(norm)
    return "\n".join(ordered)


# ---------------------------------------------------------------- summarise

def summarise(text, host, model):
    if not text.strip():
        return ""
    prompt = (
        "Summarise the following transcript in 3 to 5 concise sentences. "
        "Plain prose, no preamble.\n\n" + text
    )
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        log(f"summarising via Ollama ({model})...")
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read()).get("response", "").strip()
    except Exception as e:
        log(f"summary skipped (Ollama not reachable at {host}: {e})")
        return ""


# ---------------------------------------------------------------- report

def write_report(out_dir, url, full_text, timed_text, onscreen, summary, lang):
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "report.md"
    parts = [f"# Transcript\n\nSource: {url}\nDetected language: {lang}\n"]
    if summary:
        parts.append(f"## Summary\n\n{summary}\n")
    parts.append(f"## Spoken words\n\n{full_text}\n")
    if onscreen:
        parts.append(f"## On-screen text\n\n{onscreen}\n")
    parts.append("## Timed transcript\n\n```\n" + timed_text + "\n```\n")
    report.write_text("\n".join(parts), encoding="utf-8")

    (out_dir / "transcript.txt").write_text(full_text, encoding="utf-8")
    if onscreen:
        (out_dir / "onscreen.txt").write_text(onscreen, encoding="utf-8")
    return report


# ---------------------------------------------------------------- cli

def main():
    p = argparse.ArgumentParser(description="Video URL in, transcript out.")
    p.add_argument("url")
    p.add_argument("-o", "--output-dir", default="./out")
    p.add_argument("-m", "--model", default="base.en",
                   help="whisper model: tiny.en, base.en, small.en, medium.en, large-v3")
    p.add_argument("--language", default=None, help="force a language code, e.g. en")
    p.add_argument("--cookies-from-browser", default=None,
                   help="native only: chrome, firefox, safari, edge")
    p.add_argument("--cookies", default=None,
                   help="path to a Netscape cookies.txt (use this inside the container)")
    p.add_argument("--no-ocr", action="store_true")
    p.add_argument("--no-summary", action="store_true")
    p.add_argument("--keep-media", action="store_true")
    p.add_argument("--ocr-interval", type=int, default=2,
                   help="seconds between sampled frames for OCR")
    p.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    p.add_argument("--ollama-model", default=os.environ.get("OLLAMA_MODEL", "llama3.1"))
    args = p.parse_args()

    out_dir = Path(args.output_dir).resolve()
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        media = download(args.url, workdir,
                         cookies_browser=args.cookies_from_browser,
                         cookies_file=args.cookies)

        full_text, timed_text, lang = transcribe(media, args.model, args.language)
        onscreen = "" if args.no_ocr else ocr(media, workdir, args.ocr_interval)
        summary = "" if args.no_summary else summarise(full_text, args.ollama_host, args.ollama_model)

        report = write_report(out_dir, args.url, full_text, timed_text, onscreen, summary, lang)

        if args.keep_media:
            shutil.copy(media, out_dir / media.name)

    log(f"done -> {report}")
    print(report)


if __name__ == "__main__":
    main()
