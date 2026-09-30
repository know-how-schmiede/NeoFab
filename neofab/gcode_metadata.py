"""Read slicer cost metadata from text G-code and Prusa binary G-code."""

import math
import os
from pathlib import Path
import re
import struct
import zlib

def _parse_float_token(raw_value: str | None) -> float | None:
    if not raw_value:
        return None
    normalized = raw_value.strip().replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def _parse_gcode_duration_minutes(raw_value: str | None) -> int | None:
    if not raw_value:
        return None
    value = raw_value.strip().lower()
    total_minutes = 0.0

    for pattern, factor in (
        (r"(\d+(?:[.,]\d+)?)\s*(?:d|day|days)\b", 1440),
        (r"(\d+(?:[.,]\d+)?)\s*(?:h|hr|hrs|hour|hours)\b", 60),
        (r"(\d+(?:[.,]\d+)?)\s*(?:m|min|mins|minute|minutes)\b", 1),
        (r"(\d+(?:[.,]\d+)?)\s*(?:s|sec|secs|second|seconds)\b", 1 / 60),
    ):
        match = re.search(pattern, value)
        if match:
            total_minutes += (_parse_float_token(match.group(1)) or 0.0) * factor

    if total_minutes:
        return max(0, int(round(total_minutes)))

    colon_match = re.search(r"\b(\d{1,3}):(\d{2})(?::(\d{2}))?\b", value)
    if colon_match:
        first = int(colon_match.group(1))
        second = int(colon_match.group(2))
        third = int(colon_match.group(3) or 0)
        total_minutes = first * 60 + second + (third / 60 if colon_match.group(3) else 0)
        return max(0, int(round(total_minutes)))

    numeric = _parse_float_token(value)
    if numeric is not None:
        return max(0, int(round(numeric / 60)))
    return None


GCODE_METADATA_SCAN_BYTES = 2 * 1024 * 1024


def _read_gcode_metadata_lines(path: Path) -> list[str]:
    """Read only the G-code regions where slicers normally store metadata."""
    with path.open("rb") as handle:
        magic = handle.read(4)
        handle.seek(0)
        if magic == b"GCDE":
            return _read_bgcode_metadata_lines(handle)
        if path.suffix.lower() == ".bgcode":
            return []
        head = handle.read(GCODE_METADATA_SCAN_BYTES)
        file_size = handle.seek(0, os.SEEK_END)

        tail = b""
        if file_size > GCODE_METADATA_SCAN_BYTES:
            handle.seek(max(GCODE_METADATA_SCAN_BYTES, file_size - GCODE_METADATA_SCAN_BYTES))
            tail = handle.read(GCODE_METADATA_SCAN_BYTES)

    content = head if not tail else head + b"\n" + tail
    return content.decode("utf-8", errors="ignore").splitlines()


def extract_gcode_metadata(path: Path) -> dict[str, float | int]:
    metadata: dict[str, float | int] = {}
    try:
        for raw_line in _read_gcode_metadata_lines(path):
            line = raw_line.strip()
            lower = line.lower()

            if "duration_min" not in metadata:
                time_match = re.search(r";\s*time\s*:\s*(\d+(?:[.,]\d+)?)\s*$", lower)
                if time_match:
                    seconds = _parse_float_token(time_match.group(1))
                    if seconds is not None:
                        metadata["duration_min"] = max(0, int(round(seconds / 60)))

            if "duration_min" not in metadata and "first layer" not in lower and any(
                token in lower for token in ("estimated printing time", "estimated print time", "print time", "printing time")
            ):
                duration = _parse_gcode_duration_minutes(line)
                if duration is not None:
                    metadata["duration_min"] = duration

            if "filament_m" not in metadata:
                filament_bracket_m_match = re.search(r"filament\s+used\s*\[(mm|m)\]\s*=\s*(.+)$", lower)
                if filament_bracket_m_match:
                    value = _parse_filament_total(filament_bracket_m_match.group(2))
                    if value is not None:
                        metadata["filament_m"] = value / 1000 if filament_bracket_m_match.group(1) == "mm" else value

            if "filament_m" not in metadata:
                filament_m_match = re.search(r"filament\s+used.*?(\d+(?:[.,]\d+)?)\s*m\b", lower)
                if filament_m_match:
                    value = _parse_float_token(filament_m_match.group(1))
                    if value is not None:
                        metadata["filament_m"] = value

            if "filament_m" not in metadata:
                filament_mm_match = re.search(r"filament\s+used.*?(\d+(?:[.,]\d+)?)\s*mm\b", lower)
                if filament_mm_match:
                    value = _parse_float_token(filament_mm_match.group(1))
                    if value is not None:
                        metadata["filament_m"] = value / 1000

            if "filament_g" not in metadata:
                filament_bracket_g_match = re.search(
                    r"(?:filament\s+used|total\s+filament\s+used)\s*\[g\]\s*=\s*(.+)$",
                    lower,
                )
                if filament_bracket_g_match:
                    value = _parse_filament_total(filament_bracket_g_match.group(1))
                    if value is not None:
                        metadata["filament_g"] = value

            if "filament_g" not in metadata:
                filament_g_match = re.search(
                    r"(?:filament\s+used|filament\s+weight|total\s+filament).*?(\d+(?:[.,]\d+)?)\s*g\b",
                    lower,
                )
                if filament_g_match:
                    value = _parse_float_token(filament_g_match.group(1))
                    if value is not None:
                        metadata["filament_g"] = value

            if len(metadata) == 3:
                break
    except (OSError, ValueError, struct.error, zlib.error):
        return metadata

    return metadata


def _parse_filament_total(raw_value: str) -> float | None:
    # Prusa lists tools with comma separators; keep decimal commas for single values.
    separator = r"[,;]" if "." in raw_value else r",\s+|;"
    values = [_parse_float_token(token) for token in re.split(separator, raw_value.strip())]
    if not values or any(value is None or value < 0 or not math.isfinite(value) for value in values):
        return None
    return sum(values)


def _read_bgcode_metadata_lines(handle) -> list[str]:
    """Read bounded INI blocks, skipping thumbnails and stopping before toolpaths.

    Format: https://github.com/prusa3d/libbgcode/blob/main/doc/specifications.md
    Supports uncompressed and Deflate metadata as exported by PrusaSlicer.
    Unsupported metadata encodings/compression are skipped, never scanned as text.
    """
    header = handle.read(10)
    magic, version, checksum_type = struct.unpack("<4sIH", header)
    if magic != b"GCDE" or version != 1 or checksum_type not in (0, 1):
        return []
    file_size = handle.seek(0, os.SEEK_END)
    handle.seek(10)
    lines_by_type = {3: [], 4: []}
    remaining = GCODE_METADATA_SCAN_BYTES
    for _ in range(1024):
        header = handle.read(8)
        if not header:
            break
        block_type, compression, raw_size = struct.unpack("<HHI", header)
        if block_type == 1:
            break
        if block_type not in (0, 2, 3, 4, 5):
            raise ValueError("Unknown BGCODE block")
        stored_size = raw_size
        if compression:
            extra = handle.read(4)
            stored_size = struct.unpack("<I", extra)[0]
            header += extra
        parameter_size = 6 if block_type == 5 else 2
        checksum_size = 4 if checksum_type == 1 else 0
        if handle.tell() + parameter_size + stored_size + checksum_size > file_size:
            raise ValueError("Truncated BGCODE block")
        parameters = handle.read(parameter_size)
        if (block_type not in lines_by_type or compression not in (0, 1)
                or parameters != b"\x00\x00" or max(raw_size, stored_size) > remaining):
            handle.seek(stored_size + checksum_size, os.SEEK_CUR)
            continue
        remaining -= max(raw_size, stored_size)
        payload = handle.read(stored_size)
        if checksum_size:
            expected = struct.unpack("<I", handle.read(4))[0]
            actual = zlib.crc32(payload, zlib.crc32(parameters, zlib.crc32(header)))
            if actual != expected:
                raise ValueError("Invalid BGCODE metadata checksum")
        if compression == 1:
            decoder = zlib.decompressobj()
            payload = decoder.decompress(payload, raw_size + 1)
            if not decoder.eof or decoder.unused_data:
                raise ValueError("Invalid BGCODE Deflate stream")
        if len(payload) != raw_size:
            raise ValueError("Invalid BGCODE metadata size")
        lines_by_type[block_type].extend(payload.decode("utf-8").splitlines())
    # Full print statistics take priority over the printer's summary.
    return lines_by_type[4] + lines_by_type[3]
