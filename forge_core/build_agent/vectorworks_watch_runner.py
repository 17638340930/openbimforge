import os
import time
from pathlib import Path
from typing import List

from forge_core.build_agent.vectorworks_execute import build_run_summary, run_handoff


STALE_LOCK_SECONDS = 10 * 60


def _is_retry_or_primary_handoff(path: Path) -> bool:
    return path.name.startswith("nexus_payload_") and path.suffix == ".json"


def _lock_path(handoff_path: str) -> Path:
    return Path(f"{handoff_path}.running")


def _done_marker_path(handoff_path: str) -> Path:
    return Path(f"{handoff_path}.done")


def _failed_marker_path(handoff_path: str) -> Path:
    return Path(f"{handoff_path}.failed")


def find_pending_handoffs(handoff_root: str) -> List[str]:
    root = Path(handoff_root)
    if not root.exists():
        return []

    pending: List[str] = []
    for handoff_path in sorted(root.glob("nexus_payload_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not _is_retry_or_primary_handoff(handoff_path):
            continue
        if handoff_path.name.endswith(".result.json"):
            continue
        if handoff_path.name.endswith(".fix-request.json"):
            continue
        lock_path = _lock_path(str(handoff_path))
        if lock_path.exists():
            try:
                lock_age = time.time() - lock_path.stat().st_mtime
            except OSError:
                lock_age = 0
            if lock_age <= STALE_LOCK_SECONDS:
                continue
            lock_path.unlink(missing_ok=True)
        if _done_marker_path(str(handoff_path)).exists():
            continue
        if _failed_marker_path(str(handoff_path)).exists():
            continue
        result_path = handoff_path.with_suffix(".result.json")
        if result_path.exists():
            continue
        pending.append(str(handoff_path))
    return pending


def run_pending_handoffs(handoff_root: str, once: bool = False) -> List[dict]:
    results: List[dict] = []
    for handoff_path in find_pending_handoffs(handoff_root):
        lock_path = _lock_path(handoff_path)
        lock_path.write_text(str(time.time()), encoding="utf-8")
        try:
            result = run_handoff(handoff_path)
            results.append(result)
            result_path = Path(str(handoff_path)).with_suffix(".result.json")
            if result_path.exists():
                # JY: Let Vectorworks/Windows finish flushing the JSON before the
                # marker tells the front-end the task is fully consumable.
                deadline = time.time() + 2
                while time.time() < deadline:
                    try:
                        if result_path.stat().st_size > 0:
                            break
                    except OSError:
                        pass
                    time.sleep(0.05)
            marker_path = (
                _done_marker_path(handoff_path)
                if result.get("ok")
                else _failed_marker_path(handoff_path)
            )
            marker_path.write_text(build_run_summary(result), encoding="utf-8")
        finally:
            lock_path.unlink(missing_ok=True)
        if once:
            break
    return results


def watch_handoffs(
    handoff_root: str,
    interval_seconds: float = 3.0,
    once: bool = False,
) -> List[dict]:
    results: List[dict] = []
    while True:
        batch = run_pending_handoffs(handoff_root)
        results.extend(batch)
        if once:
            return results
        time.sleep(interval_seconds)


def start_vectorworks_runner(
    payload_root: str,
    interval_seconds: float = 3.0,
    once: bool = False,
) -> None:
    try:
        import vs  # type: ignore

        vs.AlrtDialog(
            "Nexus Synthesis Node (Constructor) activated.\n"
            f"Orchestration Root: {payload_root}\n"
            "System is now monitoring Transit-Payloads for Constructive Synthesis."
        )
    except Exception:
        print(f"[Nexus-Constructor] Node activated. Monitoring: {payload_root}")
    watch_handoffs(payload_root, interval_seconds=interval_seconds, once=once)


if __name__ == "__main__":
    project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
    runtime_root = os.environ.get(
        "OPENBIMFORGE_RUNTIME_ROOT",
        os.path.join(project_root, "forge_runtime"),
    )
    handoff_root = os.path.join(runtime_root, "handoffs")
    print(watch_handoffs(handoff_root, once=True))
