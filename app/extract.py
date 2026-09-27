"""Content extraction for uploaded materials (txt/md/pdf)."""
from __future__ import annotations

import io


def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from file bytes. Never raises: any failure (corrupt
    pdf, no text layer, encoding issues) yields "" so upload is not blocked."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("txt", "md"):
        return data.decode("utf-8", errors="ignore")
    if ext == "pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""   # 损坏 pdf / 无文本层 → 空正文，不阻塞上传
    return ""
