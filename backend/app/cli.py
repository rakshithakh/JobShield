"""Maintenance commands:  python -m app.cli purge   (clears stored job text whose retention window has passed)"""
import sys

from .config import get_settings
from .db.repository import purge_expired_inputs
from .db.session import make_engine, make_session_factory


def main(argv: list[str]) -> int:
    if argv[:1] != ["purge"]:
        print("usage: python -m app.cli purge")
        return 2
    s = get_settings()
    with make_session_factory(make_engine(s))() as db:
        n = purge_expired_inputs(db)
    print(f"purged input text from {n} analyses")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
