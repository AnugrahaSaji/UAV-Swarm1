import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@unittest.skip("Pre-freeze draft replaced by hierarchical_swarm/security.py and test_security.py")
class TestSwarmSMTIntegration(unittest.TestCase):
    def test_legacy(self):
        pass
