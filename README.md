# William Keenan

I build evidence-first machine-learning and AI systems: chronological evaluation,
calibrated uncertainty, auditable agent coordination, and decision support that
keeps people in control.

## Research and machine learning

### [Waggle + Kea](https://github.com/willykeenan/waggle-kea) — open source

Waggle is an experimental protocol for compact, typed coordination between
machine agents. Kea is its separate decoder and audit layer: it registers codec
manifests, checks payload integrity, reconstructs deterministic messages,
surfaces uncertainty, records hash-chained history, and never grants authority
to act.

The public TypeScript reference implementation includes:

- canonical encoding and content-addressed identity;
- closed-world packet and envelope schemas, causal-parent integrity, global
  idempotency collision detection, and guarded atomic ledger batches;
- typed HTTP failure behavior, read-only defaults, deterministic replay, and
  explicit `not-evaluated` policy semantics;
- a public BANKING77 intent-classification benchmark with matched models, five
  fixed seeds, paired uncertainty, calibration, risk–coverage, leakage and
  typo-stress controls, and all 77 per-intent results;
- Node 22/24 CI, coverage gates, CodeQL, dependency auditing, clean-package
  smoke tests, and a separate full benchmark-reproduction workflow.

In the exploratory BANKING77 evaluation, word-plus-character features improved
macro-F1 from `0.8915` to `0.9119` over the matched word-only model. The paired
difference was `+0.0203` with a 2,000-draw 95% bootstrap interval of
`[+0.0140, +0.0274]`. All 3,050 train-disjoint predictions preserved their
route through direct, JSON, and Waggle/Kea handoffs; the finite fault suite had
zero detectable-fault accepts and Kea granted zero authority. The repository
contains the pinned source contract, code, text-free predictions, complete
metrics, checksums, and one-command reproduction.

A bounded local study reused one Qwen3-14B native prefix state across six
source-separated branches on Apple Metal. It preserved exact outputs and beat
repeated full-text reconstruction after branch two, but it did **not** beat the
stronger cached-prefix or warmed fresh-native controls. I rejected the broader
efficiency claim and published the negative result with the code.

### [Financial Complaint Intelligence](https://github.com/willykeenan/financial-complaint-intelligence)

An end-to-end NLP evaluation on public CFPB complaint data, covering temporal
holdouts, deduplication, TF-IDF versus DistilBERT, confidence calibration,
risk–coverage analysis, error analysis, and human-review routing. The locked
experiment favored the simpler baseline—disciplined model selection over model
hype.

### HEATWAKE — private ML research

HEATWAKE explores whether temporally causal representations of market
microstructure can support calibrated probabilistic forecasting. Its source,
datasets, and operational details remain private; this overview describes the
research method and verified outcome only.

The evaluation system is designed around:

- **preregistration:** hypotheses, baselines, primary metrics, thresholds,
  compute limits, stopping rules, and failure outcomes are frozen in advance;
- **chronological testing:** train, development, calibration, and sealed-test
  partitions are ordered in time, with purge and embargo boundaries;
- **causal feature controls:** every model input must be available at prediction
  time; future events, labels, identifiers, and post-cutoff data are excluded;
- **leakage tripwires:** cross-partition duplication, future-prefix invariance,
  identifier injection, target overlap, lineage mismatch, time reversal, lag
  tests, and impossible performance all fail closed;
- **matched controls:** candidates are compared with frozen, equally informed
  baselines, shuffled-label controls, and modality ablations;
- **uncertainty before promotion:** probabilistic loss and calibration matter
  more than a favorable point estimate; paired time-grouped uncertainty must
  clear the frozen criterion;
- **reproducible provenance:** datasets, transformations, contracts,
  checkpoints, and outcomes are bound through deterministic manifests and
  retained failure artifacts;
- **abstention:** ambiguous evidence, failed controls, or missing provenance
  selects no model and emits no forecast.

In one bounded retrospective development study, the candidate produced a
favorable point estimate against its frozen baseline but failed the
preregistered uncertainty criterion. I selected no model, kept the final test
sealed, emitted no signal, and retained the outcome as insufficient evidence.
That result demonstrates that the framework can reject an attractive model
instead of weakening the threshold after the fact.

HEATWAKE does **not** claim market edge, profitability, trading readiness,
production deployment, or live operational use.

## Applied system

### [Pointer](https://github.com/willykeenan/pointer-app)

A Mac desktop-assistance prototype combining screen context and voice input to
provide low-friction, plain-language guidance. It reflects the same design
priority as my ML work: make complex systems legible and preserve human review.

## How I work

- Define the claim and falsifier before choosing a model.
- Protect temporal causality and data lineage before measuring performance.
- Compare strong, equally informed baselines—not decorative controls.
- Calibrate uncertainty and route low-confidence cases to human review.
- Keep model output separate from operational authority.
- Publish negative results when the evidence does not clear the frozen gate.
