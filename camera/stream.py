#!/usr/bin/env python3
"""Real-time MJPEG camera streamer for Pi Camera (OV5647).
Access at http://<pi-ip>:8090/
"""
import io
import logging
import socketserver
from http import server
from threading import Condition
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput

PAGE = """\
<html><head><title>Pi Camera Stream</title></head>
<body style="margin:0;background:#000;display:flex;justify-content:center;align-items:center;height:100vh">
<img src="stream.mjpg" style="max-width:100%;max-height:100vh"/>
</body></html>
"""


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            content = PAGE.encode("utf-8")
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
            self.send_header(
                "Content-Type",
                "multipart/x-mixed-replace; boundary=FRAME",
            )
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except Exception as e:
                logging.warning("Client disconnected: %s", str(e))
        else:
            self.send_error(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress per-request logs


class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"size": (1280, 720), "format": "RGB888"},
        controls={"FrameRate": 30},
    )
    picam2.configure(config)
    output = StreamingOutput()
    picam2.start_recording(MJPEGEncoder(), FileOutput(output))
    print("Stream started at http://0.0.0.0:8090/")
    print("Open http://100.101.93.23:8090/ in your browser")
    try:
        srv = StreamingServer(("0.0.0.0", 8090), StreamingHandler)
        srv.serve_forever()
    finally:
        picam2.stop_recording()
