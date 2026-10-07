import hashlib

from pathlib import Path
from uuid import uuid4

from app.config import settings


MAX_UPLOAD_SIZE = 25 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".xlsx",
}


class FileValidationError(Exception):
    pass


def validate_excel_filename(
    filename: str,
):
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            "Only .xlsx Excel files are supported."
        )


def validate_file_size(
    content: bytes,
):
    if not content:
        raise FileValidationError(
            "The uploaded file is empty."
        )

    if len(content) > MAX_UPLOAD_SIZE:
        raise FileValidationError(
            "The uploaded file is larger than 25 MB."
        )


def calculate_sha256(
    content: bytes,
) -> str:
    return hashlib.sha256(
        content
    ).hexdigest()


def save_report_file(
    content: bytes,
    original_filename: str,
    case_id: int,
    report_type: str,
) -> str:

    suffix = Path(
        original_filename
    ).suffix.lower()

    folder = (
        Path(settings.upload_dir)
        / f"case_{case_id}"
        / "groww"
    )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    stored_name = (
        f"{report_type.lower()}_"
        f"{uuid4().hex}"
        f"{suffix}"
    )

    path = folder / stored_name

    path.write_bytes(content)

    return str(path)