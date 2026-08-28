# Introduction figure candidate scorecard

Scoring: data/flow fidelity 40, text correctness 25, final-size legibility 20, composition 10, aesthetics 5.

## Concept overview

| Candidate | Route / adapted grammar | Score | Verdict |
| --- | --- | ---: | --- |
| `routeA-concept-linear` | Python / linear evidence journey | 100 | Authoritative semantic blueprint. All five stages, 218→109 evidence and boundary are exact; editable SVG/PDF; PDF glyph floor 9 pt. |
| `routeA-concept-hub` | Python / hub-and-branches | 94 | Accurate and reproducible, but the first-time reader sees the orchestrator before the WAV→MP4 journey. |
| `routeB-concept-linear` | GPT-Image / RAG-style pipeline | 97 | Text and order are unusually accurate, but it is a generated layout study rather than an editable deterministic figure. |
| `routeB-concept-hub` | GPT-Image / evaluation-loop hub | 93 | Accurate text and strong composition; route-A linear candidate explains the hands-on sequence faster. |
| `routeB-concept-final-high` | GPT-Image high / blueprint-guided linear journey | 100 | **Winner by explicit user direction to use a generated figure.** Exact five stages, all numbers/text, 1→5 arrows and claim boundary passed semantic audit. |
| `routeB-concept-icon-isometric-v2` | GPT-Image high edit / icon-rich technical assembly | 100 | **Current winner.** Exact semantics plus distinct audio, GPU-face, rigged bust, MRQ camera and verified MP4 icon systems; strongest three-glance readability. |

Selected generated file: `docs/assets/audio2face-hands-on/figures/concept-overview-generated-gpt2-v2-icon-rich.png`.

## Runtime architecture

| Candidate | Route / adapted grammar | Score | Verdict |
| --- | --- | ---: | --- |
| `routeA-architecture-lanes` | Python / parallel runtime lanes | 100 | Authoritative semantic blueprint. GPU1 inference, GPU0 render, MRQ→FFmpeg→Artifacts and VNC boundary are explicit; PDF glyph floor 8 pt. |
| `routeA-architecture-stack` | Python / layered artifact stack | 92 | Clean and accurate but does not expose the FFmpeg branch as clearly as the lane layout. |
| `routeB-architecture-lanes` | GPT-Image / systems swimlanes | 76 | Disqualified: visual arrow placement makes solver→FFmpeg look like the frame path and MRQ terminates at the boundary rather than FFmpeg. |
| `routeB-architecture-stack` | GPT-Image / exploded layered assembly | 88 | Attractive and readable but omits the project-local FFmpeg node required by the architecture contract. |
| `routeB-architecture-final-high-attempt1` | GPT-Image high / two-reference swimlanes | 78 | Disqualified: despite the prompt, it drew solver→FFmpeg and MRQ→footer. Retained as negative evidence. |
| `routeB-architecture-final-high` | GPT-Image high edit / corrected swimlanes | 100 | **Winner by explicit user direction.** All node labels and seven directed connections, including MRQ→FFmpeg→Artifacts, passed semantic audit. |
| `routeB-architecture-icon-flat-v2` | GPT-Image high edit / flat icon system | 98 | Accurate and highly readable; icon hierarchy is strong but less visually distinctive than the isometric candidate. |
| `routeB-architecture-icon-isometric-v2` | GPT-Image high edit / isometric technical plate | 100 | **Current winner.** All eight nodes have coherent icons, seven-edge flow remains exact, and visual richness improves without reducing label clarity. |

Selected generated file: `docs/assets/audio2face-hands-on/figures/cli-architecture-generated-gpt2-v2-icon-rich.png`.

## Semantic audit

- Every selected arrow was checked from source to destination. The generated architecture final has exactly: CLI→GPU1, GPU1→solver, solver→ACE, GPU0→ACE, ACE→MRQ, MRQ→FFmpeg, FFmpeg→Artifacts.
- Model version and layout revision are not conflated.
- GPU assignments, endpoint, raw/output sample counts and codecs trace to successful local manifests.
- VNC is shown only as observation/initial-auth surface, never as the repeatable production path.
- No figure claims NVIDIA CES-demo parity, exact Claire↔MetaHuman geometry, extended tongue/head completion, or unconditional Linux Vulkan success.
- Route A candidates remain authoritative reproducible blueprints. Route B high-quality finalists are used in the tutorial because the user explicitly requested generated images; they are conceptual schematics, not empirical evidence panels.

## Novice/generalized v3 redesign

| Figure | Candidate grammars | Winner | Reason |
| --- | --- | --- | --- |
| Concept | Route A linear journey; Route A hub-and-branches; Route B isometric five-card journey | `routeB-concept-general-isometric-v3` | General reusable flow, no sample counts/ports/GPU, exact 1→5 reading, configurable choices visible |
| Architecture | Route A plain linear cards; Route A layered stack; Route B novice isometric left-to-right path | `routeB-architecture-novice-linear-v3` | Plain language, four unambiguous arrows, no internal runtime jargon, strongest novice three-glance test |

The prior architecture candidates remain as negative/iteration evidence. The new tutorial winners are `concept-overview-general-generated-v3.png` and `cli-architecture-novice-generated-v3.png`.
