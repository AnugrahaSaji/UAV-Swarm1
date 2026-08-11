import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@unittest.skip("Legacy draft replaced by hierarchical_swarm/topology.py and test_topology.py")
class TestSwarmManager(unittest.TestCase):
    def test_legacy(self):
        pass

