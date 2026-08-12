from __future__ import annotations

import io
import stat
import zipfile
from pathlib import Path


def extract_repository_zip(
    content: bytes,
    destination: Path,
    *,
    max_archive_bytes: int = 50_000_000,
    max_extracted_bytes: int = 150_000_000,
    max_files: int = 10_000,
) -> None:
    if len(content) > max_archive_bytes:
        raise ValueError("Repository archive exceeds compressed size limit")
    destination.mkdir(parents=True, exist_ok=False)
    resolved_destination = destination.resolve()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if len(members) > max_files:
            raise ValueError("Repository archive contains too many files")
        if sum(item.file_size for item in members) > max_extracted_bytes:
            raise ValueError("Repository archive exceeds extracted size limit")
        roots = {Path(item.filename).parts[0] for item in members if Path(item.filename).parts}
        if len(roots) != 1:
            raise ValueError("Repository archive must have exactly one root directory")
        for item in members:
            if item.flag_bits & 0x1:
                raise ValueError("Encrypted repository archives are not supported")
            mode = item.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if file_type not in {0, stat.S_IFREG}:
                raise ValueError("Repository archive contains a non-regular file")
            relative = Path(*Path(item.filename).parts[1:])
            if not relative.parts:
                continue
            target = (destination / relative).resolve()
            if resolved_destination not in target.parents:
                raise ValueError("Repository archive contains an unsafe path")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))
