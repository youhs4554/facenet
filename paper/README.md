# Py-Feat Test-Only Benchmark Paper

The manuscript evaluates the pretrained Py-Feat `Detectorv2` pipeline on
deterministic AFLFP and DISFA test cohorts. Aggregate JSON, sample-level CSV,
generated LaTeX tables, and vector figures are retained with the source.
Dataset images and videos are not redistributed.

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
