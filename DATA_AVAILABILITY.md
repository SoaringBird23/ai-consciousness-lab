# Data and Code Availability

This document states exactly what is released with this repository, what is
not, and why. It accompanies the preprint *Growing Rather Than Training: A
Pre-Registered Developmental System, and the Read-Only Nature of Its Workspace*.

## 1. Code — released

All source modules are in the repository root: `main.py` (main loop, clock,
persistence), `background.py` (state ODE), `language.py` (retrieval-based inner
speech), `workspace.py`, `self_model.py`, `vocal.py`, `predictor.py`,
`spont.py`, `milieu.py`, `motor.py`, `affect.py`, and the remaining modules.
Runtime is Python 3.9; see `requirements.txt`. License: **MIT** (see `LICENSE`).

## 2. Pre-registrations and results — released

Every experiment has a frozen pre-registration written **before** data
collection and a results file for its outcome:

- `experiments/prereg_*.json` — hypotheses, metrics, pass/fail thresholds,
  frozen before collection; the `created` field is the time evidence.
- `experiments/results_*.json` — outcomes, including negative results.
- `experiments/analyze_*.py` — the analysers that produce those outcomes.

Negative and failed predictions are reported at the same level of detail as
positive ones. That is a design commitment of this project, not an oversight.

## 3. Caregiver corpus — NOT redistributed

The caregiver speech corpus is derived from the **CHILDES / TalkBank Mandarin
sub-corpus**. Its terms of use require that the original data not be
redistributed, so neither `corpus_raw/` nor the derived `corpus/*.json` are
included here. What is included:

- `corpus/MANIFEST.md` — provenance, the download command, and the required
  citation of the original corpus and of MacWhinney's CHILDES manual.
- `tools/build_corpus.py` — the script that rebuilds the corpus from the
  downloaded source.

Anyone wishing to reproduce the language layer must obtain the source data from
TalkBank directly and cite it.

## 4. Raw runtime state — not included

Per-instance directories (`state_*/`) contain the per-tick state streams
(`trajectory.jsonl`, `inner_speech.jsonl`, `vocalizations.jsonl`,
`attribution.jsonl`, …). These are excluded here because of their volume and
because they are individual life histories rather than reusable datasets.
Small frozen snapshots referenced by specific analyses (for example
`experiments/baseline_pre_E1/`) **are** included where an analysis depends on
them. Further raw data can be made available on reasonable request.

## 5. Scope of the reported results

All reported results come from the **accelerated line** (`--time-scale 1e9`;
measured at roughly 5×10²–10³ × real time). The real-time main line is young.
Accelerated-line results are treated as **pathway evidence, not final data**,
and are labelled as such throughout the preprint.

## 6. Licensing summary

| Material | License |
|---|---|
| Code (`*.py`, `*.sh`) | MIT — see `LICENSE` |
| Pre-registrations, results, docs, paper | CC BY 4.0 |
| Caregiver corpus (CHILDES-derived) | not distributed; governed by TalkBank terms |

## 7. Citation

See `CITATION.cff`.
