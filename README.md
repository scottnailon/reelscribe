# reelscribe

A single command video-to-transcript tool. Give it a video URL and it returns
the spoken words, any on-screen text, and an optional summary as Markdown.
Runs natively or as a portable container, fully on your own machine. No cloud
services required.

## What it does

1. Downloads the video with yt-dlp
2. Transcribes the audio with faster-whisper (runs on CPU)
3. Reads burned-in or on-screen text with tesseract OCR
4. Summarises the transcript using a local Ollama model (optional)
5. Writes a combined `report.md` plus plain text transcripts

## Requirements

- Python 3.10 or newer
- ffmpeg
- tesseract (only needed for the OCR step)
- Ollama running somewhere (only needed for the summary step)

## Install

Native:

```bash
# macOS system deps
brew install ffmpeg tesseract

pip install -r requirements.txt
```

Container (identical behaviour on any machine):

```bash
docker build -t reelscribe .
```

## Usage

Native:

```bash
python reelscribe.py "https://example.com/video" --cookies-from-browser chrome
```

Container (output lands in `./out`, models cached in `./models`):

```bash
./run.sh "https://example.com/video" --cookies cookies.txt
```

## Output

Each run creates a folder under your output directory containing:

| File | Contents |
|------|----------|
| `report.md` | Summary, spoken words, on-screen text, timed transcript |
| `transcript.txt` | Plain spoken words |
| `onscreen.txt` | Deduplicated on-screen text (if OCR ran) |

## Authentication

Some sites require a logged-in session to fetch a video.

- Native: pass `--cookies-from-browser chrome` (or firefox, safari, edge)
- Container: export a Netscape `cookies.txt` and pass `--cookies cookies.txt`

Your `cookies.txt` holds a live session and is git-ignored by default. Never
commit it.

## Configuration

| Flag | Default | Purpose |
|------|---------|---------|
| `-m, --model` | `base.en` | Whisper model: tiny.en, base.en, small.en, medium.en, large-v3 |
| `--language` | auto | Force a language code, e.g. en |
| `--no-ocr` | off | Skip on-screen text extraction |
| `--no-summary` | off | Skip the summary step |
| `--keep-media` | off | Keep the downloaded video file |
| `--ocr-interval` | 2 | Seconds between sampled frames for OCR |
| `--ollama-host` | `http://localhost:11434` | Ollama endpoint (or set `OLLAMA_HOST`) |
| `--ollama-model` | `llama3.1` | Summary model (or set `OLLAMA_MODEL`) |

If Ollama is unreachable, the summary is skipped and everything else still runs.

## Responsible use

This is a general transcription utility. Use it on content you own or have
permission to process, and respect the terms of service of any platform you
download from.

## License

MIT. See [LICENSE](LICENSE).
