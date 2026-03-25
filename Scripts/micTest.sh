#!/bin/bash

# micTest-ffmpeg.sh - Record and playback test audio using PulseAudio and ffmpeg

# Set default duration
DURATION="${1:-3}"

# Make alert sounds
for i in {1..3}; do
  paplay /usr/share/sounds/freedesktop/stereo/bell.oga
  sleep 0.4
done

# Temporary file for the audio
AUDIO_FILE="/dev/shm/mic_test.wav"

echo "Recording for $DURATION seconds... 🎙️"
ffmpeg -f pulse -i default -t "$DURATION" -acodec pcm_s16le -ar 44100 -ac 1 "$AUDIO_FILE" -y -loglevel error

echo "Playing back... 🔊"
ffplay -nodisp -autoexit "$AUDIO_FILE" -loglevel error

rm -f "$AUDIO_FILE"
