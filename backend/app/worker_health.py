from .db import SessionLocal
from .monitoring.engine import worker_status


def main():
    try:
        with SessionLocal() as db:
            return 0 if worker_status(db)["status"] == "running" else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
