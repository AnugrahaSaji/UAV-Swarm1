import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@unittest.skip("Obsolete scratch test replaced by tests/test_core_quality.py")
class TestCoreHardening(unittest.TestCase):
    def test_legacy(self):
        pass


