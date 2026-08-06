# MIMIC-Extract with Apptainer (Singularity)

Upstream MIMIC-Extract assumes Docker and a network-attached Postgres. Neither exists on Compute Canada: Docker needs root, and `--network host` is blocked. This directory is the port that works there — Apptainer instead of Docker, and Postgres reached over a **Unix socket** at `data/pg_socket/` instead of TCP.

That socket is the single fact that explains most of what looks odd below. A socket is a file on one node's filesystem, so every extraction job has to land on the *same node* as the Postgres that setup started. That's why setup and extraction are separate jobs, why you pass `PGHOST` around by hand, and why parallel submission needs `--nodelist`.

If you have Docker and root, use `docker/` instead and ignore all of this.

## RAM requirements

**Budget 100 GB.** See [docs/RESOURCE_ESTIMATES.md](../docs/RESOURCE_ESTIMATES.md) for the breakdown — the extractor pivots the whole chartevents table in memory, so this isn't padding.

## Quick start

### 1. Load modules

```bash
module load postgresql apptainer
```

### 2. Build images (one-time)

From the project root:

```bash
cd research/MIMIC_Extract
apptainer build apptainer/mimextract.sif apptainer/mimic-extract.def
apptainer build apptainer/postgres.sif docker://postgres:15
```

Build the Postgres SIF locally rather than letting Apptainer pull `docker://postgres:15` at run time. Running straight from a docker URI mounts it through FUSE, which CVMFS drops partway through a long job — that's the "Transport endpoint is not connected" failure below.

### 3. Place MIMIC-III data

Put MIMIC-III CSV files in `data/mimiciii/1.4/` (same as Docker setup).

### 4. Run the setup job (SLURM)

Submit from the project root — the job scripts use relative paths and will silently look in the wrong place otherwise. Setup loads MIMIC-III, builds the derived concept tables, and then **leaves Postgres running** so the extraction jobs have something to connect to.

```bash
cd /path/to/MIMIC_Extract
sbatch apptainer/jobs/job_setup_postgres.sh
```

If running interactively (not via SLURM):

```bash
cd /path/to/MIMIC_Extract
nohup bash apptainer/start_postgres_apptainer.sh > postgres.log 2>&1 &
# Wait ~30s, then:
PGHOST=$PWD/data/pg_socket bash apptainer/run_all_scenarios_apptainer.sh
```

### 5. Run all scenarios (sequential, single job)

```bash
cd /path/to/MIMIC_Extract
sbatch apptainer/job_slurm.sh
```

Output goes to `data/curated/{scenario_name}/`.

## Parallel execution (per-scenario jobs)

The 13 scenarios are independent, so running them as separate jobs turns a multi-day sequential run into hours — assuming the queue cooperates. The catch is the shared socket:

```bash
# 1. Setup once — loads data, builds concepts, leaves Postgres up
sbatch apptainer/jobs/job_setup_postgres.sh

# 2. Wait for it to finish, then fan out. PGHOST must be the node setup landed on;
#    submit_all.sh passes it through as --nodelist so the jobs can find the socket.
PGHOST=<hostname> bash apptainer/jobs/submit_all.sh
```

Or one at a time: `sbatch apptainer/jobs/job_pop5000.sh`.

See [apptainer/jobs/README.md](jobs/README.md) for details.

## Sequential execution (single job)

```bash
#!/bin/bash
#SBATCH --job-name=mimic-extract
#SBATCH --mem=100G
#SBATCH --cpus-per-task=8
#SBATCH --time=72:00:00
#SBATCH --output=mimic_extract_%j.log

module load apptainer

cd $SLURM_SUBMIT_DIR/research/MIMIC_Extract

# Start Postgres in background
bash apptainer/start_postgres_apptainer.sh &
PGPID=$!
sleep 30
until PGPASSWORD=mimic psql -h localhost -U mimic -d mimic -c '\q' 2>/dev/null; do
  sleep 5
done

# Run all scenarios sequentially
bash apptainer/run_all_scenarios_apptainer.sh

kill $PGPID 2>/dev/null || true
```

## Troubleshooting

### "Disk quota exceeded"

Loaded MIMIC-III is **50–80 GB** of Postgres data, which is more than a Compute Canada home directory holds. Point it at scratch:

```bash
POSTGRES_DATA_DIR=$SCRATCH/mimic_postgres sbatch apptainer/jobs/job_setup_postgres.sh
```

If you also move `PG_SOCKET_DIR`, every extraction job needs the same value — they find Postgres by path, and a mismatch just looks like "connection refused".

### "Transport endpoint is not connected"

CVMFS dropped the FUSE mount out from under the running container. Almost always means Postgres is being run straight from `docker://postgres:15` instead of a local SIF:

```bash
apptainer build apptainer/postgres.sif docker://postgres:15
```

The setup job builds it automatically if it's missing, but do it on the login node beforehand — building inside the job eats into the walltime and sometimes doesn't finish.

### Extraction jobs can't connect

Check they landed on the same node as setup. The socket is a file on that node's filesystem and there's no fallback to TCP, so a job scheduled elsewhere fails with a connection error that says nothing about node placement.

### `USE_NATIVE_POSTGRES=1`

Escape hatch for when FUSE is misbehaving badly enough that containerised Postgres won't stay up. Runs Postgres from the `postgresql` module directly, no container. Fewer moving parts, but you're then at the mercy of whatever Postgres version the cluster provides.

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `PGHOST` | localhost | Set to the setup job's node, or the socket directory path |
| `PGPORT` | 5432 | Irrelevant on the socket path |
| `MIMIC_DATA_PATH` | `data/mimiciii/1.4` | Where the MIMIC-III CSVs live |
| `CURATED_OUTPUT` | `data/curated` | One subdirectory per scenario |
| `MIMEXTRACT_SIF` | `apptainer/mimextract.sif` | Built from `mimic-extract.def` |
| `POSTGRES_SIF` | `apptainer/postgres.sif` | Build locally — see the FUSE note above |
| `POSTGRES_DATA_DIR` | `data/postgres_data` | Move to scratch if you're quota-limited |
