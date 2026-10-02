"""Course export/import as a single zip package."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

FORMAT = "endaq-course-package/1"


def export_package(course_meta: dict, course_doc: dict, survey_files: list[tuple[str, bytes]],
                   background: tuple[str, bytes] | None = None) -> bytes:
    """survey_files and background are (filename, bytes) pairs."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        manifest = {"format": FORMAT, "course": course_meta,
                    "surveys": [n for n, _ in survey_files],
                    "background": background[0] if background else None}
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
        z.writestr("course.json", json.dumps(course_doc, indent=1))
        for name, data in survey_files:
            z.writestr(f"surveys/{name}", data)
        if background:
            z.writestr(f"background/{background[0]}", background[1])
    return buf.getvalue()


def read_package(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("format") != FORMAT:
            raise ValueError("not an enDAQ course package")
        course = json.loads(z.read("course.json"))
        surveys = {n.split("/", 1)[1]: z.read(n) for n in z.namelist() if n.startswith("surveys/") and not n.endswith("/")}
        bg = None
        for n in z.namelist():
            if n.startswith("background/") and not n.endswith("/"):
                bg = (n.split("/", 1)[1], z.read(n))
    return {"manifest": manifest, "course": course, "surveys": surveys, "background": bg}
