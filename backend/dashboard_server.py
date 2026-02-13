# backend/dashboard_server.py
"""
Simple HTTP server to host the dashboard on the VPS.
Serves index.html on port 9323.
"""

import http.server
import socketserver
import os

PORT = 9323
DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_files")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        print(f"[Dashboard] {args[0]}")


def main():
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"[Dashboard] Serving on http://0.0.0.0:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
