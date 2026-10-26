from email import policy
from email.parser import BytesParser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import re


ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT / "uploads"
MAX_UPLOAD_SIZE = 100 * 1024 * 1024


def page(message=""):
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Upload files to this repository</title>
  <style>
    body {{ max-width: 680px; margin: 12vh auto; padding: 0 24px; color: #17211d; font: 16px/1.5 system-ui, sans-serif; }}
    h1 {{ font-size: 2rem; line-height: 1.15; }}
    form {{ display: grid; gap: 16px; margin-top: 28px; }}
    input, button {{ font: inherit; }}
    input[type=file] {{ padding: 18px; border: 1px solid #9aa9a1; border-radius: 6px; }}
    button {{ justify-self: start; padding: 10px 18px; border: 0; border-radius: 4px; color: white; background: #176b4d; cursor: pointer; }}
    .message {{ margin-top: 24px; padding: 12px 16px; background: #edf4ef; border-left: 4px solid #176b4d; }}
    .hint {{ color: #52615a; }}
  </style>
</head>
<body>
  <h1>Upload files to this repository</h1>
  <p class="hint">Files are saved in the <strong>uploads/</strong> folder. Maximum total upload size: 100 MB.</p>
  <form action="/upload" method="post" enctype="multipart/form-data">
    <input type="file" name="files" multiple required>
    <button type="submit">Upload files</button>
  </form>
  {message}
</body>
</html>"""


class UploadHandler(BaseHTTPRequestHandler):
    def send_page(self, content, status=200):
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        self.send_page(page())

    def do_POST(self):
        if self.path != "/upload":
            self.send_error(404)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid content length")
            return
        if content_length <= 0 or content_length > MAX_UPLOAD_SIZE:
            self.send_error(413, "Upload must be between 1 byte and 100 MB")
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data;"):
            self.send_error(400, "Expected a multipart file upload")
            return

        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii")
            + self.rfile.read(content_length)
        )
        if not message.is_multipart():
            self.send_error(400, "Could not read uploaded files")
            return

        UPLOAD_DIR.mkdir(exist_ok=True)
        saved = []
        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data" or part.get_param("name", header="content-disposition") != "files":
                continue
            filename = part.get_filename()
            if not filename:
                continue
            filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
            filename = re.sub(r"[\x00-\x1f\x7f]", "", filename).strip()
            if filename in ("", ".", ".."):
                continue

            destination = UPLOAD_DIR / filename
            stem, suffix = destination.stem, destination.suffix
            version = 1
            while destination.exists():
                destination = UPLOAD_DIR / f"{stem}_{version}{suffix}"
                version += 1
            destination.write_bytes(part.get_payload(decode=True) or b"")
            saved.append(destination.name)

        if not saved:
            self.send_page(page('<p class="message">No files were selected.</p>'), 400)
            return

        file_list = "".join(f"<li>{escape(name)}</li>" for name in saved)
        result = f'<div class="message"><strong>Uploaded {len(saved)} file(s) to uploads/:</strong><ul>{file_list}</ul></div>'
        self.send_page(page(result))


def main():
    parser = argparse.ArgumentParser(description="Upload files into this repository's uploads/ folder.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), UploadHandler)
    print(f"Upload page: http://127.0.0.1:{args.port}")
    print("Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nUpload server stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()