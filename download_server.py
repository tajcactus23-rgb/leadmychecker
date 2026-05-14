#!/usr/bin/env python3
"""
Simple HTTP Server with Download Support
"""
import http.server
import socketserver
import os

PORT = 12000

class DownloadHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Add download header for specific files
        if self.path.endswith('.py') or self.path.endswith('.html'):
            self.send_response(200)
            self.send_header('Content-Disposition', 'attachment')
            self.send_header('Content-Type', 'application/octet-stream')
        else:
            self.send_response(200)
        
        # Use default handler
        super().do_GET()

os.chdir('/workspace/project')
with socketserver.TCPServer(("", PORT), DownloadHandler) as httpd:
    print(f"Server with download at port {PORT}")
    httpd.serve_forever()