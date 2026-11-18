#!/usr/bin/env python3
"""Daily/weekly Ubuntu application + MariaDB/MySQL backups (Python 3, Linux)."""
import argparse
import datetime as dt
import fcntl
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(os.environ.get("BACKUP_ROOT", "/srv/backups"))
WEB = Path(os.environ.get("BACKUP_WEB", "/var/www"))
CNF = Path(os.environ.get("BACKUP_DB_CNF", "/etc/mysql/backup-client.cnf"))
DUMP_BIN = os.environ.get("BACKUP_DUMP_BIN", "mariadb-dump")


def log(message: str) -> None:
    line = f"[{dt.datetime.now().astimezone().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    with (ROOT / "backup.log").open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")


def verify(directory: Path) -> None:
    archive = directory / "apps.tar.gz"
    with tarfile.open(archive, "r:gz") as bundle:
        for _ in bundle:
            pass
    with gzip.open(directory / "databases.sql.gz", "rb") as stream:
        while stream.read(1024 * 1024):
            pass
    if (directory / "databases.sql.gz").stat().st_size == 0:
        raise RuntimeError("Database archive is empty")


def cleanup(parent: Path, prefix_kind: str, days: int) -> None:
    cutoff = time.time() - (days + 1) * 86400
    for item in parent.iterdir():
        if not item.is_dir() or item.stat().st_mtime >= cutoff:
            continue
        if prefix_kind == "daily":
            try:
                dt.date.fromisoformat(item.name)
            except ValueError:
                continue
        else:
            import re
            if not re.fullmatch(r"\d{4}-W\d{2}", item.name):
                continue
        shutil.rmtree(item)


def daily(today: dt.date) -> None:
    if not WEB.is_dir() or not CNF.is_file():
        raise RuntimeError("Missing web directory or MySQL credentials file")
    if not shutil.which(DUMP_BIN):
        raise RuntimeError(f"Missing dump command: {DUMP_BIN}")
    target = ROOT / "daily" / today.isoformat()
    if target.exists():
        log(f"Backup already exists: {target}")
        return
    with tempfile.TemporaryDirectory(prefix=".tmp.", dir=ROOT / "daily") as tmp_name:
        tmp = Path(tmp_name)
        log("Starting daily backup")
        with tarfile.open(tmp / "apps.tar.gz", "w:gz") as archive:
            archive.add(WEB, arcname=".")
        cmd = [DUMP_BIN, f"--defaults-extra-file={CNF}", "--all-databases",
               "--single-transaction", "--quick", "--routines", "--events", "--triggers"]
        with (tmp / "databases.sql.gz").open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb") as compressed:
                result = subprocess.run(cmd, stdout=compressed, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Database export failed with status {result.returncode}")
        verify(tmp)
        tmp.rename(target)
    cleanup(ROOT / "daily", "daily", 7)
    log(f"Daily backup complete: {target}")


def weekly(today: dt.date) -> None:
    source = ROOT / "daily" / today.isoformat()
    if not (source / "apps.tar.gz").is_file() or not (source / "databases.sql.gz").is_file():
        raise RuntimeError(f"Missing daily backup: {source}")
    destination = ROOT / "weekly" / f"{today.isocalendar().year}-W{today.isocalendar().week:02d}"
    if destination.exists():
        log(f"Weekly backup already exists: {destination}")
        return
    with tempfile.TemporaryDirectory(prefix=".tmp.", dir=ROOT / "weekly") as tmp_name:
        tmp = Path(tmp_name)
        shutil.copy2(source / "apps.tar.gz", tmp / "apps.tar.gz")
        shutil.copy2(source / "databases.sql.gz", tmp / "databases.sql.gz")
        verify(tmp)
        tmp.rename(destination)
    cleanup(ROOT / "weekly", "weekly", 56)
    log(f"Weekly backup complete: {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["daily", "weekly"], nargs="?", default="daily")
    args = parser.parse_args()
    os.umask(0o077)
    (ROOT / "daily").mkdir(parents=True, exist_ok=True)
    (ROOT / "weekly").mkdir(parents=True, exist_ok=True)
    try:
        with (ROOT / ".backup.lock").open("a") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another backup is running")
            if args.mode == "daily":
                daily(dt.date.today())
            else:
                weekly(dt.date.today())
    except (OSError, RuntimeError, tarfile.TarError) as exc:
        log(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
