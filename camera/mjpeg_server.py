#!/usr/bin/env python3
"""Lightweight MJPEG HTTP streamer using rpicam-vid subprocess.
No picamera2/numpy dependency - uses rpicam-vid CLI directly.
"""
import argparse
import io
import subprocess
import socketserver
from http import server
from threading import Condition, Thread

PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html><head><title>Pi Camera Stream</title>
<style>
  body {{ margin:0; background:#111; display:flex; flex-direction:column;
         justify-content:center; align-items:center; height:100vh; font-family:sans-serif; }}
  img {{ max-width:100%%; max-height:90vh; border:2px solid #333; border-radius:8px; }}
  h3 {{ color:#0f0; margin:8px; font-size:14px; }}
</style></head>
<body>
<h3>Pi Camera Live &mdash; {width}x{height} @ {fps}fps</h3>
<img src="/stream.mjpg" />
</body></html>
"""


class MJPEGOutput:
    """Collects MJPEG frames from rpicam-vid stdout."""
    def __init__(self):
        self.frame = None
        self.condition = Condition()
        self._buffer = bytearray()

    def feed(self, data):
        self._buffer.extend(data)
        # MJPEG frames are delimited by SOI (FFD8) and EOI (FFD9)
        while True:
            soi = self._buffer.find(b'\xff\xd8')
            if soi == -1:
                break
            eoi = self._buffer.find(b'\xff\xd9', soi + 2)
            if eoi == -1:
                break
            frame = bytes(self._buffer[soi:eoi + 2])
            self._buffer = self._buffer[eoi + 2:]
            with self.condition:
                self.frame = frame
                self.condition.notify_all()


class StreamingHandler(server.BaseHTTPRequestHandler):
    output = None
    page_html = ""

    def do_GET(self):
        if self.path == "/":
            content = self.page_html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Age", 0)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type",
                             "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            try:
                while True:
                    with self.output.condition:
                        self.output.condition.wait()
                        frame = self.output.frame
                    self.wfile.write(b"--FRAME\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(
                        f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except Exception:
                pass
        else:
            self.send_error(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class ThreadedHTTPServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def reader_thread(proc, output):
    """Read rpicam-vid stdout and feed frames to output."""
    while True:
        chunk = proc.stdout.read(65536)
        if not chunk:
            break
        output.feed(chunk)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--quality", type=int, default=80,
                        help="JPEG quality 1-100")
    args = parser.parse_args()

    output = MJPEGOutput()

    # Launch rpicam-vid producing MJPEG to stdout
    cmd = [
        "rpicam-vid",
        "--codec", "mjpeg",
        "--width", str(args.width),
        "--height", str(args.height),
        "--framerate", str(args.fps),
        "--quality", str(args.quality),
        "--timeout", "0",          # run forever
        "--nopreview",
        "-o", "-",                 # output to stdout
    ]
    print(f"Starting: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)

    # Read frames in background thread
    t = Thread(target=reader_thread, args=(proc, output), daemon=True)
    t.start()

    # Set up HTTP handler
    StreamingHandler.output = output
    StreamingHandler.page_html = PAGE_TEMPLATE.format(
        width=args.width, height=args.height, fps=args.fps)

    srv = ThreadedHTTPServer(("0.0.0.0", args.port), StreamingHandler)
    print(f"MJPEG stream: http://0.0.0.0:{args.port}/stream.mjpg")
    print(f"HTML viewer:  http://0.0.0.0:{args.port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        proc.wait()
        print("Stream stopped.")


if __name__ == "__main__":
    main()
