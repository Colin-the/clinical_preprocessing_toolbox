# Resources

The configuration that decides what the extractor pulls and what it throws away. Editing files in here changes the output far more than anything in the job scripts does — and it changes it silently, since nothing validates these against the data.

## The two that matter

**`itemid_to_variable_map.csv`** — maps MIMIC-III item IDs onto variable names, at two levels of grouping. LEVEL1 is fine-grained, LEVEL2 is what the extractor groups on. The many-to-one mapping exists because MIMIC-III spans two charting systems (CareVue and MetaVision) that assigned different IDs to the same measurement, and because the same concept often gets charted under several names. Miss an ID and you lose that measurement for a chunk of the cohort, with nothing to indicate it happened.

The `STATUS`/`READY` columns gate whether a row is used at all — an item ID being present in this file doesn't mean it's being extracted.

**`variable_ranges.csv`** — clipping bounds per variable. Values outside get dropped as charting errors before anything downstream sees them. The bounds are deliberately wide: they're meant to catch data-entry mistakes (a heart rate of 900), not unusual patients (a heart rate of 250). Tightening them toward clinical normals quietly deletes the sick patients the models are supposed to find.

## Widening the variable set

`CORE_VITAL_LEVEL2` at the top of `../mimic_direct_extract.py` restricts output to the seven bedside vitals shared with the `EHR-Dataset-Processing` pipeline. That constant is what makes the two pipelines comparable, so adding a variable means touching three things together:

1. `itemid_to_variable_map.csv` — the item IDs and their LEVEL2 name
2. `variable_ranges.csv` — bounds for the new variable
3. `CORE_VITAL_LEVEL2` — otherwise it gets extracted and then filtered straight back out

If the point is a cross-pipeline comparison, the `EHR-Dataset-Processing` side needs the same variable added to its `VITALS` dict. Note the naming conventions differ: Title Case here (`Heart Rate`), lowercase there (`heart rate`).

## The rest

- `outcome_data_spec.json`, `static_data_spec.json` — expected schema of the output tables
- `Rohit_itemid.txt` — MIMIC-II to MIMIC-III item ID correspondence, upstream reference material
- `item_id_stat.csv` — per-item frequency counts, useful when deciding whether an ID is worth including
- `testing_schemas.pkl` — fixtures for `../notebooks/Testing mimic_direct_extract.ipynb`
