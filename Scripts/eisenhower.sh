#!/usr/bin/env bash

WEBKIT_DISABLE_DMABUF_RENDERER=1 luakit \
  --class eisenhower \
  --name eisenhower \
  -U \
  "http://localhost:9876/eisenhower" &
