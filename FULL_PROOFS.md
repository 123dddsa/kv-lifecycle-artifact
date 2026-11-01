# Full Proofs and Mechanization Logs

Companion to §3 of the anonymous paper. Every proof below is either
complete or reduces to a one-line argument; the TLA+ models and TLC logs in
`theory/tla/` are the machine-checkable counterpart.

## 1. Model

A *trace* is a finite sequence over
`A = {START, ABORT, POLL, DELIVER, QUIESCE, IDLE}`.
A trace induces a state `(P, D, H, R)` where

- `P` : pending scoped operations,
- `D` : delivered completions (a multiset of scoped operations),
- `H` : observed-but-not-yet-delivered completions (held),
- `R` : released owners (requests whose ownership ended).

A scoped operation is `o = (c, r, a, d)`; `owner(o) = r`.

**Observation.** For a trace `τ`, the separated observation `obs_S(τ)` records
every event with its scoped operation; the merged observation `obs_M(τ)` is the
homomorphism that collapses each `POLL` followed (at any later point) by the
`DELIVER` of the same completion into a single `COMPLETE` event at the POLL,
erasing the relative order of delivery and release.

## 2. Monitor soundness (Theorem `thm:sound`)

**Claim.** Under A1–A5, a report of C1, C2, or C3 on `τ` implies the generating
execution violates the corresponding rule.

**Proof.** C1 reports iff there is `o ∈ D` with `owner(o) ∈ R`. A1 says `τ` is a
faithful projection of the execution (no hidden or reordered events), and the
monitor computes `D` and `R` from `τ` alone. Therefore the execution contains a
delivery of `o` after `owner(o)` was released, which is exactly the C1
predicate. C2 reports iff `|D[o]| > 1`, and by A1 each element of `D[o]` is a
distinct observed delivery of the same scoped operation; a delivery of a
terminal completion twice is the C2 predicate. C3 reports iff a terminal,
fairly-progressed receive of `o` is still in `P` at quiescence; A2 rules out
transport loss, A4 gives fair progress, A5 gives a terminating quiesce, so the
unresolved pending receive is a real liveness violation. C4 is excluded: it is
fairness-gated and audited, not asserted. ∎

## 3. Identity counting law (Theorem `thm:count`)

**Claim.** Let `k ≥ 2` scoped operations share one bare request ID `r`. Under
request-keyed monitoring the duplicate rule fires exactly `k−1` times; under
scoped identity it fires zero times.

**Proof.** Request-keyed monitor: `D` is keyed by `r`, so the first delivery
creates the entry and each of the remaining `k−1` deliveries finds an existing
entry and reports once. Scoped monitor: `D` is keyed by `(c,r,a,d)`; if the `k`
operations differ in at least one component they are pairwise distinct keys, so
no delivery ever finds an existing key. The law is definitional; the empirical
content is that a real fan-out connector instantiates distinct keys under
controlled child schedules. ∎

## 4. Merged delivery is unreachable for C1 (Theorem `thm:merged`)

**Claim.** Under merged semantics the stale-send target is unreachable at every
horizon (`q = 0`).

**Proof.** A stale completion requires a delivery event that happens after the
owner is released. Merged semantics has no separate delivery: consumption is
attached to the observing POLL. Any merged execution therefore consumes a
completion at a POLL, and release happens only at later steps; by induction on
the trace no state can contain a delivery after release. Hence C1 is
unreachable by construction; TLC confirms this on the finite model (39 states
generated, 12 distinct, `NoC1` and `MergedEmpty` hold). ∎

## 5. Impossibility under merged observations (Theorem `thm:impossibility`)

**Claim.** There exist two executions with identical merged observation but
different C1 truth; hence no deterministic monitor over merged observations is
both sound and complete for C1.

**Proof.** Let `τ₁ = START, POLL, ABORT, DELIVER` and
`τ₂ = START, POLL, DELIVER, ABORT`, with the same completion value produced at
the POLL. Under `obs_M` both traces collapse to `START, COMPLETE, ABORT`
(the homomorphism attaches the delivery to the poll and erases its position
relative to ABORT). In `τ₁` the delivery follows the free (`freed = TRUE` at
DELIVER), so C1 holds; in `τ₂` the delivery precedes the free, so C1 fails. A
deterministic monitor is a function of its observation; equal observations
force equal verdicts, so it errs on one of the two traces. A randomized monitor
errs with positive probability on one of them, so no merged monitor is both
sound and complete. ∎

*Corollary (false-negative oracle).* A merged-semantics CI gate reports success
whenever the window occurs, which is what the 0/200 versus 74/200 counterfactual
measures: the abstract monitor reaches no target at any horizon (Theorem
`thm:merged`) while the concrete scheduler still asserts.

## 6. Separation is sufficient and exact (Theorem `thm:sufficiency`)

**Claim.** Under A1–A3, the scoped monitor reports C1 for `τ` iff `τ` contains a
DELIVER whose scoped owner is in `R`, and reports at that DELIVER.

**Proof.** C1 is the predicate `o ∈ D ∧ owner(o) ∈ R`. A1 makes `τ` a faithful
projection and A3 makes observed completions component facts, so evaluating the
predicate at each DELIVER fires exactly on violating traces and at the violating
step. C2–C4 are evaluated independently and cannot mask C1. ∎

*Detection delay.* The report occurs at the first DELIVER after the release, so
the delay is at most one delivery plus the poll interval that observes it; the
directed schedule `START, POLL, ABORT, DELIVER, POLL, DELIVER` is the six-step
minimum witness (the separated model's TLC counterexample).

## 7. Identity is necessary for unique attribution (Theorem `thm:identity`)

**Claim.** Every identity coarser than `(c,r,a,d)` admits observationally
equivalent distinct operations; the four-tuple is the coarsest separating
identity and yields the counting law.

**Proof.** Coarsening forgets at least one component. Choose `o₁ ≠ o₂` differing
only in that component; then `id'(o₁) = id'(o₂)`. The executions delivering
`o₁` then `o₂`, and `o₂` then `o₁`, produce identical `id'` observations, so no
monitor can attribute the delivery to a specific operation nor decide C2
identically on both. Separating every component gives distinct keys, removes the
equivalence, and reduces to Theorem `thm:count` (`k−1` insensitive versus zero
scoped alerts). ∎

## 8. Geometric first-discovery law and non-adaptive lower bound

**Proposition `thm:geo`.** If candidates are independent with hit probability
`q_H > 0`, the first-discovery index is geometric:
`Pr[K > k] = (1−q_H)^k`, and the median is `⌈log 0.5 / log(1−q_H)⌉`.

**Proof.** Independence gives `Pr[K > k] = (1−q_H)^k` by the product rule. The
median is the smallest `k` with `(1−q_H)^k ≤ 0.5`, i.e. the stated ceiling. ∎

**Theorem `thm:lb`.** Let `q*_H = max_π q^π_H(s)` over schedule distributions
`π(·|s)`. Any non-adaptive strategy with i.i.d. candidates of hit probability
`p ≤ q*_H` has `E[K] = 1/p ≥ 1/q*_H`, with equality iff `p = q*_H`.

**Proof.** For independent trials with hit probability `p ≤ q*_H`,
`E[K] = Σ_{k≥0} (1−p)^k = 1/p ≥ 1/q*_H` by `thm:geo`. We make no optimality
claim for the uniform policy: the DP `q^π_H` is linear in the transition
distribution `π(·|s)`, so the maximum over the simplex is attained at a vertex,
and uniform weighting is a reference policy only; §6.2 shows that six weighted
policies move the calibrated median by at most a factor 1.20. ∎

## 9. Audit completeness over a finite assumption space

**Proposition (informal).** Let `𝔄` be a pre-registered finite set of
single-factor assumptions of the oracle. If exactly one assumption is violated,
the single-factor intervention that flips it produces a control trace on which
the audited monitor's verdict changes, and the intervention identifies the
violated assumption.

**Proof sketch.** Each intervention flips one assumption and leaves the others
fixed; by definition of the finite space the audit evaluates the monitor on one
trace per intervention. If the monitor is sound for the remaining assumptions,
the only intervention that changes its verdict is the violated one; the audit
therefore either recovers the violated assumption or reveals that the monitor is
insensitive to it (an audited defect). The 296 audited records instantiate this
argument; labels are researcher-provided and frozen before the intervention. ∎

## 10. Mechanization log (TLC 2.19, Java 11, 4 workers)

| Model | Config | States (generated/distinct) | Result |
|---|---|---|---|
| `KVLifecycle.tla` | `MC_merged.cfg` | 39 / 12 | No error; `NoC1` and `MergedEmpty` hold |
| `KVLifecycle.tla` | `MC_separated.cfg` | 102 / 30 | `NoC1` violated; six-step counterexample |
| `IdentityCounting.tla` | `MC_identity_k2.cfg` | 5 / 4 | No error; `alerts_ins = 1`, `alerts_scoped = 0` |
| `IdentityCounting.tla` | `MC_identity_k3.cfg` | 13 / 8 | No error; `alerts_ins = 2`, `alerts_scoped = 0` |

Raw logs: `TLC_merged.log`, `TLC_separated.log`, `TLC_identity_k2.log`,
`TLC_identity_k3.log`. Search depth is bounded (six transitions for the merged
and separated models; the counting models are finite permutations), so the
merged result is a bounded check, not a proof of safety — the paper states this
explicitly.

