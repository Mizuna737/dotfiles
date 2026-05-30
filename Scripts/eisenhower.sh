#!/usr/bin/env bash

pgrep -f "webkitView.py.*eisenhower" > /dev/null && exit 0

WEBKIT_DISABLE_DMABUF_RENDERER=1 exec python3 "$(dirname "$0")/webkitView.py" \
  --class Eisenhower \
  --name eisenhower \
  "http://localhost:9876/eisenhower"
