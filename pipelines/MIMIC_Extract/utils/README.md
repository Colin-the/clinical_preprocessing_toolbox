# Utils

Upstream's bare-metal build route, plus a couple of local additions. **You probably don't want the bare-metal route** — use `../apptainer/` on nibi or `../docker/` anywhere with Docker. This directory is kept because the SQL and the imputation code in it are still used by those paths.

## Upstream build route

`Makefile` + `setup_user_env.sh` + `build_curated_from_psql.sh` are the original "install everything yourself" flow: source the environment, then `make build_curated_from_psql`. It needs conda, a local Postgres you've already loaded, and mimic-code checked out as a sibling directory two levels up.

`setup_user_env.sh` still has upstream's own username and database host hardcoded, so it will not work unedited.

## Actually used by the container paths

**`niv-durations.sql`** — builds the `nivdurations` concept table. Not part of mimic-code's own concept set, but MIMIC-Extract needs it, so `docker/entrypoint.sh` runs this directly during setup.

**`postgres_make_extended_concepts.sh`** — the other concepts upstream mimic-code doesn't build. Includes the BigQuery-to-Postgres SQL translation (`DATETIME_DIFF` argument quoting, stripping `physionet-data.*` table qualifiers) that `entrypoint.sh` also does inline.

**`simple_impute.py`** — the imputation used on the extracted timeseries. Upstream code.

## Local additions

**`export_postgres_to_duckdb.py`** — dumps the loaded Postgres database to a single DuckDB file.

Worth knowing why this exists: on Compute Canada the extractor reaches Postgres over a Unix socket, which means every extraction job has to be scheduled onto the same node as the job holding the database open. DuckDB is a file, not a server — so once you have one, jobs can run anywhere, and the whole node-pinning problem in `../apptainer/jobs/` goes away. Set `DB_PATH` and `entrypoint.sh` takes the DuckDB route instead.

The trade is that the export itself is slow and the file is large. See `../apptainer/jobs/job_export_duckdb.sh`.
