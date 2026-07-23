.PHONY: all assets pdf

all: pdf

assets:
	PYTHONDONTWRITEBYTECODE=1 uv run generate_assets.py

pdf: assets
	mkdir -p build ../output/pdf
	latexmk -pdf -interaction=nonstopmode -halt-on-error \
		-outdir=build pyfeat_testonly_benchmark.tex
	cp build/pyfeat_testonly_benchmark.pdf \
		../output/pdf/pyfeat_testonly_benchmark.pdf
