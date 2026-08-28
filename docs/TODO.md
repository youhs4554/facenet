# Repository Initialization

- [x] Write the root README and repository-wide ignore rules.
- [x] Consolidate the workspace under one root Git repository.
- [x] Run the available lightweight validation checks.
- [x] Review the staged files.
- [x] Create the initial commit.
- [x] Create a private GitHub repository and push the default branch.

# Py-Feat Repository Focus

- [x] Remove OpenFace source and assets from Git tracking.
- [x] Ignore the legacy local OpenFace checkout.
- [x] Refocus the root and demo documentation on Py-Feat.
- [x] Validate the Py-Feat-only tracked tree and portable test suite.
- [x] Commit the repository scope change.

# AFLFP and DISFA Benchmark Paper

- [x] Validate the raw AFLFP and DISFA dataset contracts and evaluation metrics.
- [x] Run test-only py-feat inference on deterministic evaluation cohorts.
- [x] Save machine-readable aggregate and per-sample benchmark results.
- [x] Replace the previous paper with a result-driven LaTeX manuscript.
- [x] Generate tables and figures directly from the saved benchmark results.
- [x] Compile and visually verify the final PDF and reproduction instructions.

# Weekly Report — 2026-07-24

- [x] Review the previous weekly report structure and tone.
- [x] Confirm this week's methodology and results from committed benchmark artifacts.
- [x] Draft a concise Korean weekly report focused on methodology and outcomes.
- [x] Verify all reported figures against the saved benchmark results.

# Weekly Briefing Context Revision — 2026-07-24

- [x] Review all documents and attached materials under `docs/`.
- [x] Identify Kyungpook National University Hospital and Kyungpook National University's first-year responsibilities.
- [x] Map this week's Py-Feat work to the first-year project deliverables without overstating progress.
- [x] Rewrite and verify the weekly report as a project-progress briefing.

# Weekly Briefing Visualization and Push — 2026-07-24

- [x] Select only the paper figures needed to explain the core landmark and AU results.
- [x] Add web-viewable versions of the selected figures to the weekly briefing.
- [x] Visually verify the figures and recheck the weekly report.
- [x] Commit only the weekly briefing deliverables and push the current branch.

# Weekly Briefing Structure Revision — 2026-07-24

- [x] Restructure the report around Weekly Done, Py-Feat, benchmark results, and Weekly TODO.
- [x] Retain only the project-relevant datasets, metrics, AUs, and visualizations.
- [x] Verify the shortened report against the saved benchmark artifacts.

# Target-Focused Face Case Visualizations — 2026-07-24

- [x] Confirm access to the AFLFP and DISFA source data.
- [x] Generate reproducible oral/jaw landmark and AU12/25/26 case visualizations.
- [x] Save case-selection manifests without copying source datasets.
- [x] Add the figures and scoped interpretation to the weekly report and paper.
- [x] Rebuild and visually verify the final paper PDF.

# July Research Note — 2026-07-28

- [x] Extract the blank 연구노트 template and the June example structure.
- [x] Collect July figures from the paper, benchmark results, and weekly reports.
- [x] Draw the schematics with GPT image generation under one Nature-style figure contract.
- [x] Stage the benchmark data figures and ground-truth overlay cases.
- [x] Write five Korean notes (제1호~제5호) matching the June prose format.
- [x] Fill the template, unpin the fixed row height, and size figures to avoid orphans.
- [x] Verify all 52 reported values against the saved benchmark artifacts.
- [x] Export the PDF and confirm 11 pages with no clipped or blank pages.

# Benchmark Ground-Truth Examples — 2026-07-24

- [x] Select publication-eligible AFLFP and target-relevant DISFA examples.
- [x] Visualize the source image and manual ground truth for each dataset.
- [x] Add the examples and concise annotation explanations to the weekly report.
- [x] Verify image decoding, Markdown paths, and reported ground-truth values.

# MediaPipe Blendshape V2 Webcam Demo

- [x] Review the official Blendshape V2 model card and Face Landmarker Web guide.
- [x] Add RED tests for blendshape score normalization and temporal smoothing.
- [x] Implement the standalone webcam demo with landmarks and all 52 coefficients.
- [x] Add local usage guidance and model limitations.
- [x] Run coverage, browser smoke testing, and the ECC verification loop.

# Audio2Face CLI Hands-on Tutorial — 2026-08-28

- [x] Apply ECC `orch-add-feature`, `click-path-audit`, `video-editing`, `source-command-update-docs`, and `verification-loop` with Gate 1 approval and no pre-Gate-2 commit.
- [x] Freeze a RED/GREEN documentation contract covering every canonical CLI option, required hands-on sections, figures, VNC screenshots, and result images.
- [x] Inventory 28 user control flags plus `--help`, four named shots, custom camera schema, motion/emotion configs, and verified run evidence from source.
- [x] Follow the global FIGURES contract: create a claim/evidence ledger, four Route A candidates, four Route B candidates, semantic scorecard, and reproducible Route A semantic blueprints.
- [x] Pass Route A source QA with no FAIL and PDF glyph floors of 8/9 pt; use those blueprints to generate high-quality Route B finals after explicit user direction.
- [x] Reject the first generated architecture final for incorrect solver→FFmpeg/MRQ→footer arrows, surgically regenerate it, and verify the corrected seven-edge flow before replacing the tutorial images.
- [x] Capture the actual VNC `:1` CLI help, NIM/GPU health, v3 inference progress, completed inference-only manifest, ffprobe/decode, and final triptych screens without closing the user's Bridge/Chrome surface.
- [x] Build evidence images for named/custom shots, three avatars, v2/v3, native/dynamic intensity, ACE-node blink, final triptych, and rendered face controls.
- [x] Run official v3 inference on the same audio for neutral, joy, sadness, anger, and joy-to-sadness timecoded emotion; record request/animation/geometry hashes and the inference-only boundary.
- [x] Publish `docs/audio2face-metahuman-cli-hands-on.ko.md` with step-by-step commands, all 29 help tokens, application boundaries, screenshots, output verification, and limitations.
- [x] Gate 2 review approved on 2026-08-28; the Audio2Face hands-on scope is cleared for commit.

# Audio2Face Hands-on Novice Revision — 2026-08-28

- [x] Generalize the concept figure and remove sample-specific ports, GPU names, sample/frame counts and fixed A/V values from conceptual artwork.
- [x] Redesign the architecture as a plain-language five-step left-to-right path with four audited arrows and no internal runtime jargon.
- [x] Regenerate Route A blueprints and Route B icon-led candidates; preserve prompts, candidates, scorecard and hashes.
- [x] Fix the four-camera montage label to the complete `profile-left` text with no clipped alias.
- [x] Remove v2.3-vs-v3.0 comparison content and image from the hands-on learning path; retain only a minimal legacy operation note.
- [x] Fix canonical emotion CSV expansion to ten columns with regression tests.
- [x] Produce actual Taro/UE/ACE rendered constant-joy evidence against the fresh neutral run and compose it deterministically without generated pixels.
- [x] Reframe timecoded emotion as an advanced boundary rather than rendered success evidence.
- [x] Move the canonical happy-path command and plain-Korean outcome/terms ahead of advanced internals.
- [x] Final Gate 2 review approved on 2026-08-28; the novice tutorial revision is cleared for commit.

# Audio2Face Hands-on Weekly Meeting Note — 2026-08-28

- [x] Reconcile the weekly note with the revised tutorial, current manifests, figure QA and render provenance.
- [x] Publish the Korean weekly meeting note with portable links and representative evidence figures.
- [x] Re-run focused and full Audio2Face documentation/unit verification and validate every local Markdown link.
- [x] Refocus the meeting note on completed work and verified outcomes instead of file inventory and implementation details.
- [x] Record the 2026-08-28 Gate 2 approval and commit the approved Audio2Face hands-on scope.
