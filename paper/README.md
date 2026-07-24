# Py-Feat Test-Only Benchmark Paper

The manuscript evaluates the pretrained Py-Feat `Detectorv2` pipeline on
deterministic AFLFP and DISFA test cohorts. Aggregate JSON, sample-level CSV,
generated LaTeX tables, aggregate figures, and selected target-aligned case
figures are retained with the source. Raw datasets are not redistributed; the
case manifest contains selection keys, predictions, and landmarks without raw
media.

From this directory, regenerate all derived assets and compile the PDF with:

```sh
make pdf
```

The command writes the final manuscript to:

```text
../output/pdf/pyfeat_testonly_benchmark.pdf
```

To rerun inference from `lib/py-feat-demo`, use:

```sh
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib \
PATH=/opt/homebrew/bin:$PATH \
PYTHONDONTWRITEBYTECODE=1 \
uv run benchmark_datasets.py run \
  --data-root ../../data \
  --dataset aflfp \
  --max-samples 1136 \
  --seed 42 \
  --device mps \
  --batch-size 32 \
  --output-dir ../../paper/results

DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib \
PATH=/opt/homebrew/bin:$PATH \
PYTHONDONTWRITEBYTECODE=1 \
uv run benchmark_datasets.py run \
  --data-root ../../data \
  --dataset disfa \
  --max-samples 5400 \
  --seed 42 \
  --device mps \
  --batch-size 32 \
  --output-dir ../../paper/results
```

Throughput measures only the model `detect()` call. Model initialization,
checkpoint loading, and DISFA video decoding are excluded.

When the source datasets are mounted at `data/`, regenerate the actual-face
oral/jaw landmark and AU12/25/26 case figures with:

```sh
cd ../lib/py-feat-demo
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib \
PATH=/opt/homebrew/bin:$PATH \
PYTHONDONTWRITEBYTECODE=1 \
uv run visualize_benchmark_cases.py
```

This writes the AFLFP figure, the DISFA 2-by-2 figure and compact paper strip
to `paper/figures/`, plus the auditable selection record at
`paper/results/target-case-manifest.json`. It also writes one source-image and
ground-truth example per dataset to `docs/weekly/assets/2026-07-24/`. AFLFP
cases are limited to subjects permitted for academic publication.
