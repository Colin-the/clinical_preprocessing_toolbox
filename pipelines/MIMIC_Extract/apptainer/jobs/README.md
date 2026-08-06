# Per-Scenario SLURM Jobs (Parallel Execution)

One job script per scenario, so the 13 extractions run concurrently instead of taking days in sequence. They're independent — each reads the same loaded database and writes to its own output directory — so the only thing coordinating them is that they all need to reach the same Postgres.

Each script requests its own resources via `#SBATCH` directives (typically 100G/96h for the extraction jobs), so a plain `sbatch <script>` gets the right allocation. Keep the `#SBATCH` block directly under the shebang — `sbatch` stops reading directives at the first non-comment line, so anything (even `set -euo pipefail`) placed above the block silently disables it and the job falls back to partition defaults.

## Prerequisites

1. **Setup job finished, and still running.** It loads the data, builds the concepts, and then stays alive holding Postgres open — extraction jobs connect through a Unix socket, so if the setup job ends, they all fail.
   ```bash
   cd /path/to/MIMIC_Extract    # relative paths; must be the project root
   module load postgresql apptainer
   sbatch apptainer/jobs/job_setup_postgres.sh
   ```
   **Extraction jobs must land on the same node as setup.** A socket is a file on one node's filesystem and there's no TCP fallback, so a job scheduled elsewhere fails with a bare connection error that tells you nothing about node placement. `submit_all.sh` handles this via `--nodelist`; individual `sbatch` calls don't.

2. **SIF built**: `apptainer build apptainer/mimextract.sif apptainer/mimic-extract.def`

3. **MIMIC-III CSVs** in `data/mimiciii/1.4/`

## Submit all jobs in parallel

```bash
cd /path/to/MIMIC_Extract
PGHOST=<setup-node> bash apptainer/jobs/submit_all.sh
```

Get `<setup-node>` from the setup job (`squeue -j <jobid> -o %N`). Without it the jobs go wherever the scheduler likes and can't find the socket.

## Job scripts

| Script | Scenario | Output |
|--------|----------|--------|
| job_pop5000.sh | 5000 ICU stays | data/curated/pop5000/ |
| job_min48hr.sh | Long stays (≥48h) | data/curated/min48hr/ |
| job_min18age.sh | Adults (≥18) | data/curated/min18age/ |
| job_minperc5.sh | Stricter missingness | data/curated/minperc5/ |
| job_age35_range5.sh | Ages 33–37 | data/curated/age35_range5/ |
| job_age35_range10.sh | Ages 30–40 | data/curated/age35_range10/ |
| job_age35_range15.sh | Ages 28–42 | data/curated/age35_range15/ |
| job_age45_range5.sh | Ages 43–47 | data/curated/age45_range5/ |
| job_age45_range10.sh | Ages 40–50 | data/curated/age45_range10/ |
| job_age45_range15.sh | Ages 38–52 | data/curated/age45_range15/ |
| job_age55_range5.sh | Ages 53–57 | data/curated/age55_range5/ |
| job_age55_range10.sh | Ages 50–60 | data/curated/age55_range10/ |
| job_age55_range15.sh | Ages 48–62 | data/curated/age55_range15/ |

The nine age-band jobs form a 3×3 grid — centres at 35/45/55, widths of ±5/±10/±15. That's deliberate: it separates *which* age group from *how narrow* a group, since a tighter band gives a more homogeneous cohort but leaves fewer patients to train on, and the point is finding where that trade stops paying.

## Submit individual jobs

```bash
sbatch --nodelist=<setup-node> apptainer/jobs/job_pop5000.sh
```

The `--nodelist` flag is the one thing you must add by hand (see the socket warning above); resources come from the script's own `#SBATCH` directives. `submit_all.sh` adds the nodelist for you.

## Self-contained mode (no shared Postgres)

If you genuinely can't keep all the jobs on one node, each can start its own Postgres via `START_POSTGRES=1`. It removes the node constraint entirely, at the cost of loading MIMIC-III thirteen times — hours of work and 50–80 GB of disk per job. Only worth it if node placement is the thing blocking you.
