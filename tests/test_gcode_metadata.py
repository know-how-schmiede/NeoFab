"""Run with: python3 -m unittest discover -s tests -v"""
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "neofab"))
from gcode_metadata import GCODE_METADATA_SCAN_BYTES, extract_gcode_metadata


STATS = (b"filament used [mm]=0.00, 8604.24, 0.00, 0.00, 0.00\n"
         b"filament used [g]=0.00, 25.66, 0.00, 0.00, 0.00\n"
         b"estimated printing time (normal mode)=55m 2s\n")


def block(kind, data, compression=0, checksum=True):
    payload = zlib.compress(data) if compression == 1 else data
    header = struct.pack("<HHI", kind, compression, len(data))
    if compression:
        header += struct.pack("<I", len(payload))
    parameters = struct.pack("<HHH", 2, 16, 16) if kind == 5 else b"\0\0"
    result = header + parameters + payload
    return result + (struct.pack("<I", zlib.crc32(result)) if checksum else b"")


def binary(*blocks, checksum=True):
    return struct.pack("<4sIH", b"GCDE", 1, int(checksum)) + b"".join(blocks)


class MetadataTests(unittest.TestCase):
    def parse(self, data, suffix=".bgcode"):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ("print" + suffix)
            path.write_bytes(data)
            return extract_gcode_metadata(path)

    def assert_stats(self, metadata):
        self.assertEqual(metadata["duration_min"], 55)
        self.assertAlmostEqual(metadata["filament_m"], 8.60424)
        self.assertEqual(metadata["filament_g"], 25.66)

    def test_repository_prusa_xl_file(self):
        path = Path(__file__).resolve().parents[1] / "g-code/RAC_Boden_0.4n_0.2mm_PLA_XLIS_55m.bgcode"
        if not path.exists():
            self.skipTest("Local Prusa XL sample is not present")
        self.assert_stats(extract_gcode_metadata(path))

    def test_uncompressed_and_deflate(self):
        for compression in (0, 1):
            with self.subTest(compression=compression):
                self.assert_stats(self.parse(binary(block(4, STATS, compression))))

    def test_without_checksums(self):
        self.assert_stats(self.parse(binary(block(3, STATS, checksum=False), checksum=False)))

    def test_print_metadata_priority_and_large_thumbnail(self):
        data = binary(block(3, STATS.replace(b"55m 2s", b"99m")),
                      block(5, b"x" * (GCODE_METADATA_SCAN_BYTES + 1)),
                      block(4, STATS, 1), block(1, b"not decoded"))
        self.assert_stats(self.parse(data))

    def test_corrupt_or_truncated_binary(self):
        valid = binary(block(4, STATS, 1))
        for data in (b"GCDE", valid[:20], valid[:-1],
                     valid[:-1] + bytes([valid[-1] ^ 1]), b"not bgcode\n" + STATS):
            with self.subTest(length=len(data)):
                self.assertEqual(self.parse(data), {})

    def test_unknown_version_and_compression(self):
        self.assertEqual(self.parse(b"GCDE" + struct.pack("<IH", 2, 0)), {})
        self.assertEqual(self.parse(binary(block(4, STATS, 2))), {})

    def test_oversized_metadata(self):
        payload = b"x" * (GCODE_METADATA_SCAN_BYTES + 1) + STATS
        self.assertEqual(self.parse(binary(block(4, payload, 1))), {})

    def test_legacy_text_and_decimal_comma(self):
        for suffix in (".gcode", ".gco", ".gc"):
            self.assertEqual(self.parse(b";TIME:2620\n; filament used [mm] = 6045,38\n"
                                        b"; filament used [g] = 18,18\n", suffix),
                             {"duration_min": 44, "filament_m": 6.04538, "filament_g": 18.18})

    def test_text_multiple_tools_and_large_tail(self):
        self.assert_stats(self.parse(b"G1 X0\n" * GCODE_METADATA_SCAN_BYTES + STATS, ".gcode"))

    def test_multiple_active_tools(self):
        stats = STATS.replace(b"0.00, 8604.24", b"1000.00, 8604.24").replace(b"0.00, 25.66", b"10.00, 25.66")
        result = self.parse(binary(block(4, stats)))
        self.assertAlmostEqual(result["filament_m"], 9.60424)
        self.assertAlmostEqual(result["filament_g"], 35.66)

    def test_first_layer_is_not_total_duration(self):
        self.assertEqual(self.parse(b"; estimated first layer printing time = 4m\n"
                                    b"; estimated printing time = 55m\n", ".gcode"),
                         {"duration_min": 55})


if __name__ == "__main__":
    unittest.main()
