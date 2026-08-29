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
- [x] Add the verified four-shot MetaHuman render montage to the weekly result summary.
- [x] Add verified avatar-selection, emotion and motion-intensity result comparisons to the weekly summary.
- [x] Record the 2026-08-28 Gate 2 approval and commit the approved Audio2Face hands-on scope.

# Audio2Face Natural Head Motion — 2026-08-28

- [x] Classify the feature as large and activate the ECC `orch-add-feature` gated workflow.
- [x] Verify the installed ACE 2.5 head-motion boundary and current official NVIDIA/Epic support.
- [x] Audit the CLI/config → audio clock → run-owned UE sequence → MRQ → final video control path.
- [x] Freeze a production-safe task list, RED tests, compatibility contract and OFF/ON evidence gates.
- [x] Gate 1 approved on 2026-08-29; implementation Tasks 1–8 authorized without commit.
- [x] Add Keiji Vulkan crash prevention, GPU/process/profile preflight and no-blind-retry policy to the approved plan.
- [x] Implement deterministic bounded silence-aware samples, CLI/config, artifacts, lineage, resume contract and Vulkan/GPU/UE preflight.
- [x] Verify a fresh fixed-camera Taro OFF capture/MRQ/H.264/AAC result with reused v3 inference.
- [x] Prove the original UE defect: FinalSequence was never focused/evaluated, so the FK rig had no Body-bound controls; replace evaluated ControlRig getter equality with literal section-channel verification.
- [x] Author exact run-owned Rotation X/Y/Z keys (9 channels × 109 frames) and preserve planned↔authored evidence without camera/root/source-asset fallback.
- [x] Replace the non-evaluating FK Control Rig path with direct run-owned Body/Face AnimSequence bone-track bake and prove nonzero final rendered motion.
- [x] Exhaust the four newly authorized, hypothesis-distinct Taro proof attempts (`r4`–`r7`) without Keiji source launch, Vulkan fatal, NIM restart, or source-asset mutation; stop further UE launches at the explicit budget.
- [x] Identify the post-budget UE source traps and prepare tests/code: first FK section defaults to Absolute, and Epic's skeletal transform helper selects the actor's first skeletal component instead of exact MetaHuman Body.
- [x] Run the one additionally authorized Taro proof (`20260829-095555-head-motion-on-r8-final-proof`) after helper/GPU/UE/profile/key-path preflight; preserve its pre-MRQ failure evidence and do not retry.
- [x] Fix the final proof's direct defect offline: `SetBlendType` returns `void`/Python `None`, so validate `get_blend_type()` state instead of treating the setter return as success/failure.
- [x] Run the user-authorized corrected state-readback path (`20260829-100409-head-motion-on-r9-state-readback`) once; preserve its exact-Body 0° failure and do not retry.
- [x] Replace the failed FK layer with run-owned Body/Face AnimSequence bone-track bake using Epic `IAnimationDataController`.
- [x] Build the project-local C++ wrapper and verify Body `neck_01/neck_02/head` plus Face `head` authored keys.
- [x] Complete initial native-bake Taro ON E2E (`20260829-104034-head-motion-final-e2e-r5`), then supersede it after the post-render head-timing defect was found.
- [x] Produce and verify real-pixel OFF/ON comparison, contact sheet, optical motion metrics and final verification JSON.
- [x] Fix the post-render +5-frame correction defect: bind compensation to a verified same-avatar/shot baseline, reject calibration mismatch, and record per-frame source-head mapping.
- [x] Complete synchronized canonical proof `20260829-110741-head-motion-sync-final-r7`: face lag 0, head optical lag -1 within ±1, zero-lag R² 0.994, A/V/decode PASS.
- [x] Complete independent final code review (WATCH/APPROVE) and gate review (Gate 2 READY/APPROVE); blockers 0.
- [x] Run head-motion E2E for every local MetaHuman: Taro, Keiji, Sook-ja and Jesse.
- [x] Preserve Vulkan-safe visual profiles for Keiji/Sook-ja/Jesse and never launch Keiji source clothing.
- [x] Add provenance-checked prior-attempt calibration retry for Jesse's measured capture-latency variation; retain ±1 final head-sync gate.
- [x] Produce the four-avatar H.264/AAC comparison video, atlas, per-avatar OFF/ON contact sheets and aggregate verification JSON.
- [x] Gate 2 review and commit approval granted by the user on 2026-08-29.
- [x] Produce ON MetaHuman MP4, OFF/ON comparison/contact sheet and final head-transform metrics after the stronger AnimSequence authoring + real-pixel verification gate passes.
- [x] Document the local-vs-NVIDIA boundary, public controls, safety policy, RED/GREEN evidence and completed result without claiming NVIDIA-generated head motion.

# Audio2Face CLI Hands-on Official-Quality Rewrite — 2026-08-29

- [x] Read ECC documentation/source/click-path/verification/safety skills and nature-writing methods fragments.
- [x] Freeze the Korean terminology ledger, one-sentence argument, official-source boundary and worked-example evidence.
- [x] Audit every canonical CLI flag/default/range and map each major reader action to state/artifact/result/recovery.
- [x] Capture and preserve clean numbered terminal/GUI screenshot sources without credentials or unrelated desktop content.
- [x] Add a reproducible screenshot crop/composition script and SHA/dimension provenance manifest.
- [x] Rewrite the hands-on guide into the 15-stage novice workflow with purpose/command/state/artifact/pass/recovery/boundary blocks.
- [x] Integrate the verified local head-motion path, calibration/resume contract, Taro r7 evidence and cross-avatar boundary.
- [x] Update hands-on verification metadata and documentation contract tests.
- [x] Run image/link/secret/diff visual QA plus focused/full Audio2Face tests.
- [x] Prepare review handoff; independent source and final gate reviews APPROVE, and Gate 2 commit approval was granted on 2026-08-29.
- [x] Reproduce the remaining UE GUI capture defect and isolate Bridge/Fab CEF surface restoration from the run-owned sequence itself.
- [x] Capture the real r7 Taro viewport + FinalSequence + Camera Cut/MetaHuman/HeadMotion tracks with per-process-only plugin/config overrides.
- [x] Replace the terminal substitute with the clean Unreal GUI screenshot, regenerate provenance/verification metadata, and exit the editor gracefully without saving source assets.
