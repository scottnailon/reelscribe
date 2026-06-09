#!/usr/bin/env bash
# Run reelscribe in the container. Output lands in ./out, models cached in ./models.
# Usage: ./run.sh <url> [extra reelscribe flags]
# First time:  docker build -t reelscribe .
set -euo pipefail

mkdir -p out models

docker run --rm \
  -v "$(pwd)/out:/out" \
  -v "$(pwd)/models:/models" \
  -v "$(pwd):/work" \
  reelscribe "$@" --output-dir /out
