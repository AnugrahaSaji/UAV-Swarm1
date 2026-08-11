#!/bin/bash
# Pi Camera MJPEG Stream Server
# Streams OV5647 camera at 1280x720 @ 30fps via HTTP on port 8090
#
# Usage: ./start_stream.sh
# Access: http://100.101.93.23:8090/stream.mjpg
#         http://100.101.93.23:8090/ (HTML viewer)

PORT=8090
WIDTH=1280
HEIGHT=720
FPS=30

echo "=== Pi Camera MJPEG Streamer ==="
echo "Camera: OV5647 (5MP)"
echo "Resolution: ${WIDTH}x${HEIGHT} @ ${FPS}fps"
echo ""
echo "Stream URLs:"
echo "  HTML viewer: http://$(hostname -I | awk '{print $1}'):${PORT}/"
echo "  MJPEG feed:  http://$(hostname -I | awk '{print $1}'):${PORT}/stream.mjpg"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Use rpicam-vid with inline HTTP server (TCP listener mode)
# Pipe MJPEG to a lightweight HTTP server via Python
exec python3 ~/camera/mjpeg_server.py --port $PORT --width $WIDTH --height $HEIGHT --fps $FPS
