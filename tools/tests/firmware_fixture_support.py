"""Retain real capability guards in otherwise isolated firmware fixtures."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "firmware/export/config.h"


def curtain_configuration():
    source = CONFIG.read_text(encoding="utf-8")
    blocks = re.findall(r"^#if[^\n]+\n#define HAVE_SCREEN_CURTAIN\n#endif$", source, re.MULTILINE)
    if len(blocks) != 1:
        raise AssertionError("Expected one real screen-curtain capability guard")
    return "#pragma once\n" + blocks[0] + "\n"
