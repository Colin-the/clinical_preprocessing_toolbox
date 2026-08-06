# MIMIC-Extract Docker Setup

Docker container with the same parameters as the repo's `build_curated_from_psql.sh`. Includes PostgreSQL, mimic-code, and all SQL tools needed to load raw MIMIC-III data and run the extraction pipeline.

## Prerequisites

- Docker and Docker Compose
- MIMIC-III access (PhysioNet credentialing required)
- MIMIC-III CSV files (~50GB) downloaded from PhysioNet

## Quick Start

### 1. Place MIMIC-III data

Put your MIMIC-III CSV files in the PhysioNet 1.4 structure:

```
MIMIC_Extract/
├── data/
│   ├── mimiciii/
│   │   └── 1.4/        # Your MIMIC-III files go here
│   │       ├── ADMISSIONS.csv.gz
│   │       ├── PATIENTS.csv.gz
│   │       ├── CHARTEVENTS.csv.gz
│   │       └── ... (all MIMIC-III tables)
│   └── curated/        # Output appears here
├── docker/
│   ├── docker-compose.yml
│   └── ...
```

Files can be `.csv` or `.csv.gz`. Use the exact filenames from the MIMIC-III distribution.

### 2. Build and run

```bash
cd research/MIMIC_Extract
mkdir -p data/curated

# Build the image (first time only)
docker compose -f docker/docker-compose.yml build

# Run the full pipeline
docker compose -f docker/docker-compose.yml up
```

The pipeline will:
1. Start PostgreSQL
2. Load MIMIC-III data from `data/mimiciii/1.4/`
3. Build mimic-code concepts
4. Build MIMIC-Extract extended concepts
5. Run extraction with repo parameters
6. Write output to `data/curated/`

### 3. Extract a subset (debugging)

To limit the population size (e.g., first 1000 patients):

```bash
POP_SIZE=1000 docker compose -f docker/docker-compose.yml up
```

## Parameters (matches `build_curated_from_psql.sh`)

| Parameter | Value |
|-----------|-------|
| extract_pop | 2 |
| extract_outcomes | 2 |
| extract_codes | 0 |
| extract_numerics | 2 |
| extract_notes | 0 |
| plot_hist | 0 |
| min_percent | 0 |

## Output

- `data/curated/all_hourly_data.h5` – HDF5 with tables: `patients`, `vitals_labs`, `vitals_labs_mean`, `interventions`
- Additional CSV and intermediate files in `data/curated/`

## Troubleshooting

**"No MIMIC-III files in /mimic_data"**  
Ensure `data/mimiciii/1.4/` contains the CSV files. Check the volume mount in `docker-compose.yml`.

**PostgreSQL connection errors**  
Wait for the postgres service to be healthy. The extractor will retry automatically.

**Out of memory**  
Full extraction needs ~50GB RAM. Use `POP_SIZE=1000` for testing.

## 256GB Server: Run All ML Comparison Scenarios

The setup is tuned for a 256GB RAM server. Use `run_all_scenarios.sh` to extract all dataset variants for ML comparison:

```bash
cd research/MIMIC_Extract
chmod +x docker/run_all_scenarios.sh
bash docker/run_all_scenarios.sh
```

Output is organized by scenario:

| Scenario | Output Dir | Description |
|----------|------------|-------------|
| default | `data/curated/default/` | Full dataset, default filters |
| pop2000 | `data/curated/pop2000/` | Small cohort (2000 ICU stays) |
| pop5000 | `data/curated/pop5000/` | Medium cohort (5000 ICU stays) |
| min48hr | `data/curated/min48hr/` | Long stays only (≥48 hours) |
| min18age | `data/curated/min18age/` | Adults only (≥18 years) |
| minperc5 | `data/curated/minperc5/` | Stricter missingness (drop cols >95% missing) |

Each scenario runs the full pipeline; the first run loads data and builds concepts; subsequent runs reuse the database.
