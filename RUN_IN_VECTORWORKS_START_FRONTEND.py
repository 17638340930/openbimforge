import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(r"D:\devloop\workSpace\app_codex\GenerativeBIM\openBIMForge")
RUNTIME_ROOT = PROJECT_ROOT / "forge_runtime"
HANDOFF_ROOT = RUNTIME_ROOT / "handoffs"


def _inject_path(path: Path) -> None:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


def _show(message: str) -> None:
    try:
        import vs  # type: ignore

        vs.AlrtDialog(message)
    except Exception:
        print(message)


def main() -> None:
    for path in (
        PROJECT_ROOT,
        PROJECT_ROOT / "forge_core",
        PROJECT_ROOT / "forge_core" / "design_agent",
        PROJECT_ROOT / "forge_core" / "build_agent",
    ):
        _inject_path(path)

    os.environ["PROJECT_ROOT"] = str(PROJECT_ROOT)
    os.environ["OPENBIMFORGE_ROOT"] = str(PROJECT_ROOT)
    os.environ["OPENBIMFORGE_RUNTIME_ROOT"] = str(RUNTIME_ROOT)
    os.environ["OPENBIMFORGE_OUTPUT_ROOT"] = str(HANDOFF_ROOT)
    os.environ["TEXT2BIM_PROJECT_ROOT"] = str(PROJECT_ROOT)
    os.environ["TEXT2BIM_OUTPUT_ROOT"] = str(HANDOFF_ROOT)
    os.environ["PYTHONIOENCODING"] = "utf-8"

    HANDOFF_ROOT.mkdir(parents=True, exist_ok=True)

    try:
        from forge_core.build_agent.vectorworks_watch_runner import start_vectorworks_runner

        _show(
            "openBIMForge Nexus Runner is starting.\n\n"
            f"Project Root:\n{PROJECT_ROOT}\n\n"
            f"Handoff Root:\n{HANDOFF_ROOT}\n\n"
            "Keep this Vectorworks session open while Nexus generates BIM payloads."
        )
        start_vectorworks_runner(str(HANDOFF_ROOT), interval_seconds=3.0, once=False)
    except Exception as exc:
        _show(
            "openBIMForge Nexus Runner failed to start.\n\n"
            f"{type(exc).__name__}: {exc}\n\n"
            "Check Vectorworks Script Errors and Python sys.path setup."
        )
        raise


if __name__ == "__main__":
    main()
