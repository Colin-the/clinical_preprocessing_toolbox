"""Find gallery renders the last re-render did not regenerate.

Every figure under figures/EHR-Dataset-Processing/<dataset>/ predates the 2026-08-30
vital-range fix, so all of them are stale until the gallery re-renders. Most could be
matched to an arm by filename and moved aside in advance — but not all: the numbered
exports (`mimic_iii_0000.*`) come from gallery/extract_notebook_graphs.py and carry no
arm in their name, so moving by pattern would either miss them or take figures the
re-render never puts back.

Rather than guess, this runs *after* the re-render and reports by mtime. Anything the
re-render did not touch is either genuinely stale (an arm or a plot that no longer
exists) or produced by a different tool that also needs re-running. Either way it is
something for a human to look at, which is why this only ever prints.

    python rerun/sweep_stale_figures.py --dry-run
    python rerun/sweep_stale_figures.py --since 2026-08-30T12:00:00
    python rerun/sweep_stale_figures.py --move        # -> _deprecated/pre_spo2_fix_.../figures/
"""
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from _common import EHR_ROOT

TOOLBOX_ROOT = EHR_ROOT.parent.parent
FIGURE_ROOT = TOOLBOX_ROOT / "figures" / "EHR-Dataset-Processing" / "mimic-iii"
DEST = TOOLBOX_ROOT / "_deprecated" / "pre_spo2_fix_2026-08-30" / "figures" / "mimic-iii"


def newest_mtime(root: Path) -> float:
    return max((p.stat().st_mtime for p in root.rglob("*") if p.is_file()), default=0.0)


def main() -> None:
    argv = sys.argv[1:]
    move = "--move" in argv
    since = None
    if "--since" in argv:
        since = datetime.fromisoformat(argv[argv.index("--since") + 1]).timestamp()
    unknown = set(argv) - {"--move", "--dry-run", "--since"} - (
        {argv[argv.index("--since") + 1]} if since else set())
    if unknown:
        raise SystemExit(f"unknown flag(s): {sorted(unknown)}")

    if not FIGURE_ROOT.exists():
        raise SystemExit(f"missing {FIGURE_ROOT}")

    files = sorted(p for p in FIGURE_ROOT.rglob("*") if p.is_file())
    if not files:
        raise SystemExit(f"no figures under {FIGURE_ROOT}")

    if since is None:
        # Default: the most recent render in the tree defines "this render". Anything
        # more than an hour older than it was not part of the same pass.
        since = newest_mtime(FIGURE_ROOT) - 3600

    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(since))
    fresh = [p for p in files if p.stat().st_mtime >= since]
    stale = [p for p in files if p.stat().st_mtime < since]

    print(f"figures : {FIGURE_ROOT}")
    print(f"cutoff  : {stamp}")
    print(f"fresh   : {len(fresh):,}")
    print(f"stale   : {len(stale):,} "
          f"({sum(p.stat().st_size for p in stale) / 1e6:,.1f} MB)\n")

    if not stale:
        print("Nothing stale — the re-render covered every file.")
        return

    for p in stale[:40]:
        age = time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime))
        print(f"  {age}  {p.relative_to(FIGURE_ROOT)}")
    if len(stale) > 40:
        print(f"  ... and {len(stale) - 40:,} more")

    if not move:
        print("\nReport only. Re-run with --move to set these aside, or delete them "
              "yourself once you have looked.")
        return

    for p in stale:
        dest = DEST / p.relative_to(FIGURE_ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(dest))
    print(f"\nmoved {len(stale):,} file(s) -> {DEST}")


if __name__ == "__main__":
    main()
