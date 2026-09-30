"""Set aside every artifact built with the old (too-narrow) vital ranges.

Bug register F-02: until 2026-08-30 all seven vital ceilings sat one unit below their
documented maximum, so each per-vital filter deleted its own documented maximum — most
visibly SpO2 100%, the modal reading in MIMIC. Nine of the thirteen arms are therefore
invalid (see _common.VITALS_DEPENDENT_ARMS), along with everything computed from them.

Two destinations, because /home is at 39/50 GiB and the bulk is 2.9 GB:

  BULK  -> $SCRATCH/ehr_pre_spo2_fix_2026-08-30/   (relative paths preserved)
  SMALL -> _deprecated/pre_spo2_fix_2026-08-30/    (in-repo, git-ignored)

$SCRATCH is purged periodically. This is a diffing convenience, not an archive — if
any of it matters beyond the next few weeks, copy it to /project.

Nothing here is required to make the rerun correct: rerun/regen_*.py call
create_filter_dataset directly, which writes unconditionally. Moving the files means
you can diff old against new, and means nothing stale survives if a stage is skipped.

    python rerun/quarantine_pre_spo2_fix.py --dry-run     # always do this first
    python rerun/quarantine_pre_spo2_fix.py
"""
import os
import shutil
import sys
from pathlib import Path

from _common import AGGREGATIONS, DATASET_NAME, EHR_ROOT, LABELS, VITALS_DEPENDENT_ARMS

TOOLBOX_ROOT = EHR_ROOT.parent.parent
STAMP = "pre_spo2_fix_2026-08-30"

SCRATCH = Path(os.environ.get("SCRATCH", "")) if os.environ.get("SCRATCH") else None
BULK_DEST = (SCRATCH / f"ehr_{STAMP}") if SCRATCH else None
SMALL_DEST = TOOLBOX_ROOT / "_deprecated" / STAMP


def slug(arm: str) -> str:
    """Same slug rule as create_filter_dataset (dataset_manager.py:85)."""
    return arm.replace(" ", "_").lower()


def collect():
    """(group, action, absolute path) for everything the old ranges produced.

    Explicit filenames rather than globs, deliberately: `*_oof_scores_cv.npz` would
    also sweep up `<label>_balance_oof_scores_cv.npz`, which belongs to stage H — that
    ran on the `raw` arm only (regen_balance_cv.py:66) and is NOT invalidated by this
    fix. Same trap for anything else matching `*_impact_*`.
    """
    data = EHR_ROOT / "Data" / DATASET_NAME
    logs = EHR_ROOT / "Logs" / DATASET_NAME
    items = []

    for agg in AGGREGATIONS:
        for arm in VITALS_DEPENDENT_ARMS:
            items.append(("filtered datasets", "move",
                          data / agg / f"{slug(arm)}_filtered_dataset_ehr.pkl"))
            for label in LABELS:
                for polarity in ("pos", "neg"):
                    items.append(("centroids", "move",
                                  data / agg / "centroids" / f"{label}_{arm}_{polarity}.pkl"))
        for label in LABELS:
            items.append(("out-of-fold scores", "move",
                          data / agg / f"{label}_oof_scores_cv.npz"))
        items.append(("filter change logs", "move",
                      logs / agg / "fill_missing_data_filter_log.json"))

    for agg in AGGREGATIONS:
        for arm in VITALS_DEPENDENT_ARMS:
            items.append(("admission-id sidecars", "move",
                          data / agg / f"{slug(arm)}_admission_ids.npy"))
        for label in LABELS:
            items.append(("legacy filter impact", "move",
                          data / agg / f"{label}_filter_impact.pkl"))
            items.append(("legacy filter impact", "move",
                          data / agg / f"{label}_filter_impact_diagnostics.json"))
            items.append(("CV filter impact", "move",
                          data / agg / f"{label}_filter_impact_cv.pkl"))
            items.append(("CV filter impact", "move",
                          data / agg / f"{label}_filter_impact_cv_diagnostics.json"))

    # Copied, not moved: job_j overwrites these in place, and 1.1 MB is cheap
    # insurance against a failed render leaving no figures at all.
    for pdf in sorted((EHR_ROOT / "paper_figures").glob("*.pdf")):
        items.append(("paper figures", "copy", pdf))

    return items


# Anything under Data/ that is NOT swept, stated positively so a future reader can see
# the control group was left alone on purpose rather than by oversight.
PRESERVED = """\
  raw_dataset_ehr.pkl                          raw arm — never sees `vitals`
  {long_missing_segment,long_gap,             structural filters: they accept `vitals`
   high_invalid_data}_filtered_dataset_ehr.pkl and ignore it, and are built from the
                                               RAW aggregated records, not from an
                                               outlier-filtered chain
  centroids/*_{raw,long gap,...}_*.pkl         same four arms
  {icu,mortality}_balance_*                    stage H, `raw` arm only — unaffected
  processed_record_ehr.pkl                     upstream of the bug; ingest does no clipping
"""


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]
    unknown = set(sys.argv[1:]) - {"--dry-run"}
    if unknown:
        raise SystemExit(f"unknown flag(s): {sorted(unknown)}")

    if BULK_DEST is None:
        raise SystemExit("$SCRATCH is not set — cannot place the bulk artifacts")

    items = collect()
    bulk_groups = {"filtered datasets", "centroids", "out-of-fold scores", "filter change logs"}

    present, missing, total_bytes = [], [], 0
    for group, action, path in items:
        if path.exists():
            size = path.stat().st_size
            total_bytes += size
            dest_root = BULK_DEST if group in bulk_groups else SMALL_DEST
            dest = dest_root / path.relative_to(EHR_ROOT)
            present.append((group, action, path, dest, size))
        else:
            missing.append((group, path))

    by_group = {}
    for group, action, path, dest, size in present:
        n, b, a = by_group.get(group, (0, 0, action))
        by_group[group] = (n + 1, b + size, a)

    print(f"{'group':24s} {'action':7s} {'files':>6s} {'size':>10s}  destination")
    print("-" * 88)
    for group in dict.fromkeys(g for g, _, _, _, _ in present):
        n, b, action = by_group[group]
        dest = "$SCRATCH/ehr_" + STAMP if group in bulk_groups else "_deprecated/" + STAMP
        print(f"{group:24s} {action:7s} {n:>6,} {b / 1e6:>9,.1f}M  {dest}")
    print("-" * 88)
    print(f"{'TOTAL':24s} {'':7s} {len(present):>6,} {total_bytes / 1e6:>9,.1f}M")

    if missing:
        print(f"\n{len(missing)} expected file(s) already absent:")
        for group, path in missing[:12]:
            print(f"  [{group}] {path.relative_to(EHR_ROOT)}")
        if len(missing) > 12:
            print(f"  ... and {len(missing) - 12} more")

    print(f"\nLeft in place on purpose:\n{PRESERVED}")

    if dry_run:
        print("--dry-run: nothing moved.")
        return

    for group, action, path, dest, _ in present:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if action == "move":
            shutil.move(str(path), str(dest))
        else:
            shutil.copy2(str(path), str(dest))
    print(f"\n{len(present)} file(s) set aside.")
    print(f"  bulk  : {BULK_DEST}")
    print(f"  small : {SMALL_DEST}")


if __name__ == "__main__":
    main()
