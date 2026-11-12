"""Bản thu dùng cho test Speaking.

Các file này là giọng nói thật của người học nên không commit vào repo. Test nào
cần chúng sẽ tự bỏ qua khi không tìm thấy. Muốn chạy đủ, trỏ biến môi trường
SPEAKING_TEST_FIXTURES tới thư mục chứa sample-01.m4a và part2-skill-test-01.webm.
"""

import os
import unittest
from pathlib import Path

DIR = Path(os.environ.get("SPEAKING_TEST_FIXTURES") or Path(__file__).resolve().parent / "fixtures")


def fixture_path(name):
    return DIR / name


def audio_fixture(name):
    path = DIR / name
    if not path.exists():
        raise unittest.SkipTest(
            f"thiếu bản thu {name}; đặt SPEAKING_TEST_FIXTURES tới thư mục chứa nó")
    return path.read_bytes()
