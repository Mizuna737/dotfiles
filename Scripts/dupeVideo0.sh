#!/usr/bin/env bash

OUT=/dev/video10

while true; do
  echo "Starting camera pipeline..."

  ffmpeg \
    -loglevel error \
    -f v4l2 -thread_queue_size 512 -i /dev/video0 \
    -vf "scale=1920:1080,fps=30" \
    -f v4l2 -pix_fmt yuyv422 $OUT

  echo "Camera lost → switching to black..."

  ffmpeg \
    -loglevel error \
    -f lavfi -re -i color=c=black:s=640x480:r=30 \
    -f v4l2 -pix_fmt yuyv422 $OUT

done
