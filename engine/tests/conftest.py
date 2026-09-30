import os
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRONE = ROOT / "fixtures" / "Drone_Flight.IDE"


@pytest.fixture(scope="session")
def tmpdir_session():
    with tempfile.TemporaryDirectory(prefix="endaq-test-") as d:
        yield Path(d)


@pytest.fixture(scope="session")
def drone_bundle(tmpdir_session):
    if not DRONE.exists():
        pytest.skip("fixtures/Drone_Flight.IDE not present")
    from engine.io.ide_reader import ide_to_bundle
    return ide_to_bundle(DRONE, tmpdir_session / "drone")
