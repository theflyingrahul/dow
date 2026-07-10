"""Make the in-tree ``dow`` package importable when running the tests without an
install (``pytest`` from the project root). Pytest imports this file before test
collection, so inserting the project root on ``sys.path`` is enough."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
