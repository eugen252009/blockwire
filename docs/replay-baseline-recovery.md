# H04 baseline recovery and partial-pose investigation

## Current follow-up: operation-scoped pose handoff

The [pose-handoff recovery](pose-handoff.md) refines the actual I3 contract without
changing M0 radii, BCL or safety bounds. Invariant-preserving P06 full identity is
independently verified GO. The separate frozen S05 cohort passes 9/9 with 4/4
identities; shared native movement regression passes 211/211. Reuse remains off.
The investigation below is the preserved earlier point-in-time NO-GO, not a claim
that its rejected prototypes were later accepted.

## Historical verdict before pose-handoff correction

**Historical baseline reconstructed: GO. Partial-pose cause: CONFIRMED for the
measured fixtures. Current standard replay recovery: NO-GO.** No corrective
prototype was promoted. Stateful optimizations remain disabled by default.

This investigation is a separate follow-up to the
[grounding investigation](stateful-input-execution.md), not a revision of H04,
R33, Q03, P03, QROT01, QROT02, C01 or any failed pilot. H05 remains pending genuine
owner construction. See [machine-readable evidence](evidence/replay-baseline-recovery.json)
and [the separate hash manifest](evidence/replay-baseline-recovery-hashes.json).

## Verifiable historical implementation

`bc9edcafb291517ba80a115774cafe9d27149fee5f4ed21f3361f82b3785373b`
is the QROT02 **freeze-manifest identity**, not a Git commit. Its canonical JSON
identity, saved working-tree patch and source hash map were verified. An isolated
copy was reconstructed from the historical Git base and verified patch, with
matching archived/current bytes used only when their SHA-256 matched the freeze.
All **101/101 frozen files** match, including all 51 frozen production Python
files, native sources/resources and selected tests/harnesses. The source-map
identity is `663594efae7c3d1fe115962e84e7f527e5c438ec8b036c1c49d9bdbc67c55828`.

This reconstructs the files actually covered by that manifest, **not every aspect
of the historical host, dependency installation or rendering environment**. No
checkout/reset overwrote the working tree. The current comparison arm used an
independent copy of commit `47a52ae`, with every reuse option explicitly disabled.
The installed native JAR, canonical snapshot, H04 BCL bytes, ROT90 parameters,
acceptance checks and read-only profiling were shared. Both arms ran on the same
authenticated hidden `:99` display using llvmpipe, never the visible desktop.

## Full native comparison

| Cohort / run | Source | Result | Batches reached | Blocks | Seconds |
|---|---|---|---:|---:|---:|
| AB01-A / RA-90-01 | reconstructed QROT02 | GO | 20/20 | 71/71 | 466.249 |
| AB01-B / RB-90-01 | current, all reuse off | pre-effect infrastructure failure | 0/20 | 0/71 | 0.706 |
| AB02-A / RA-90-02 | reconstructed QROT02 | GO | 20/20 | 71/71 | 468.407 |
| AB02-B / RB-90-02 | current, all reuse off | NO-GO, batch 13 | 13 reached, 12 completed | 41/71 | 305.128 |

Successful runs completed 572 runtime operations and 71 verified placement events,
with native entrance/interior/player checks and exact independent closed-save
verification. RB-90-02 stopped after 367 operations, one failed action and zero
retries, at `recorded_partial_pose_not_safely_reached`. Its ended/closed saves
agree. The first 366 dispatched typed skill actions have identical parameters and
order in the AB02 arms; different native trajectories do not imply edited BCL.

The historical gateway certificate expired between the AB01 handshakes. RB-90-01
therefore sent **no BCL action**; its terminal transport classification remains
`UNKNOWN_NO_RETRY`. The failed run was preserved, not resumed. A fresh explicitly
pinned cohort-only gateway certificate was provisioned for **both** AB02 arms;
mandatory TLS, hostname verification and native instance trust stayed enabled.
The old certificate/key were not overwritten. AB01 and AB02 are separate cohorts,
not a pooled unchanged-configuration repeatability or performance result.

## Reduced causal tests

Two closed-prefix fixtures preserve the relevant H04 mutations and actual typed
movement/view/placement parameters:

- Early face boundary: the retained GC2-90 three-block prefix and six actions.
  Its 51 production Python files were verified identical to the current arm.
- Late reach boundary: RB-90-02's 41-block prefix and five actions.

Only fixture preparation administratively restored the recorded starting pose;
geometry remained unchanged, then the fixture was sealed. Every attempt restored
that seal and bound a fresh actor. Diagnostics used the existing guarded
`AgentRuntime` and skills, not another controller or a replacement BCL program.
The preceding world prefix was retained to preserve collision dependencies;
these are reduced sequences, not a proof of globally minimal world fixtures.

| Implementation | Early suffix | Late suffix |
|---|---:|---:|
| A: exact recovered QROT02 source | 2/2 verified | 2/2 verified |
| B: current source, reuse off | 0/2 verified | 0/2 verified |
| C: current source, only motion/walking reverted to QROT02 in an isolated copy | 2/2 verified | 2/2 verified |

All four B failures reproduced the partial-pose error without use or consumption.
Every successful suffix independently added the exact requested block and consumed
one item with one use submission. All 12 trials remained grounded, used no Jump,
released controls and closed cleanly. C is **diagnostic only**: reverting the old
motor would discard the separately confirmed edge-fall correction and is not a
production solution.

### Observed causal progression

1. **Last equivalent state:** the same sealed prefix, original suffix parameters,
   grounded starting pose, settled velocity and orientation. Start positions were
   checked against the seal before measurement.
2. **First source-attributable divergence:** current motion prepares Sneak and
   leases it independently of the one-tick direction. A/C use the old coupled
   direction/Sneak release. Native inputs, ownership, velocity, bounding boxes and
   tick progression were retained privately; one input receipt is not this proof.
3. **Subsequent behavior:** changed native residual motion produces different
   settled endpoints. Later recorded M0 samples can validly accept those endpoints
   inside their unchanged radii without further motion.
4. **Failed condition:** I3 independently rejects the coarse endpoint's face or
   reach geometry; the nominal recorded target cannot serve as a robust partial-
   support preposition. Restoring only the old motor restores both suffixes.

This confirms the measured shared-motor contribution, not a complete tick-level
reconstruction of every historical failure. Ordinary timing differences can
precede the attributable lease divergence in independent complete replays.
The established directional-sample/following-hold correction remains unchanged;
these reduced failures involve M0/I3, not an M4 terminal-hold skip.

## Contract and unqualified corrections

A successful M0 proves its own settled arrival, **not the next placement**. I3
already permits a current recorded-pose proxy within 0.35 blocks, but that proxy
must satisfy native source authority, face clearance, reach and body constraints.
A nominal partial target separately requires at least 0.08 contact on both axes
and 0.25 on one. The measured early failure lacks the strict `> 0.05` face-plane
clearance; the late failure exceeds crouched reach 4.5. No boundary was relaxed.

Two separately frozen, private prototypes were tested without modifying the
recording, BCL, recorded movement samples or production package:

| Prototype | Early suffix | Late suffix | Decision |
|---|---:|---:|---|
| E01/L01: one robust inset on the existing approach segment, ordinary 0.08-radius walk plus fresh placement validation | 3/3 | 2/3 | NO-GO |
| E02/L02: same approach, additionally require admissible placement geometry inside that walking loop | 3/3 | 1/3 | NO-GO |

The first prototype can still settle just outside reach. The second can cross the
narrow admissible interval during native coast, lose its required robust-contact
predicate and terminate at the existing stuck bound. This is **not a proof that
all general corrections are impossible**; it is evidence that neither tested
correction is repeatable. Successful trials do not erase failures. No alternative
recorded route, synthesized construction strategy, tolerance increase, rescue,
teleport during measurement or action retry was introduced. Neither prototype nor
its internal arrival-predicate API was copied into production.

## Verification and remaining gates

Production runtime files remain byte-identical to the compared current arm.
New deterministic `test_recorded_pose_boundaries.py` tests preserve rejection of
coarse-but-unsafe poses, acceptance of already admissible proxies, exact face/reach
bounds, source authority and actor fencing. Three additional mutations challenge
those boundaries. These are fail-closed protection tests, **not a claimed fix**.

Final serial checks: **572 Python tests**, Gradle `check`, **197/197 skill**,
**50/50 BCL**, **47/47 Play2Code** mutations, and **10/10 TLS** checks passed.
Private prototype tests are recorded separately and do not inflate this total.

Current-source baseline recovery/repeatability is not established. New grounding
qualification, camera/Sneak/placement ablations, optimized full replays, the final
nine-case transformation cohort and final identity repeatability are **NOT RUN**:
the standard replay recovery gate failed first. Historical scoped component GOs
remain historical, not new-source qualification. Full corrected speedup and
production activation remain NO-GO. Physical F8 injection was not performed; its
implementation and existing contracts were not changed.

Next work must find and qualify a generic correction within the unchanged
recorded-position and native-safety contracts. A new implementation/policy requires
a new freeze and new run IDs; do not resume failed actions or relax constraints
to force acceptance. After correction, recover and repeat the nonoptimized replay
before enabling any optimization.

All clients and test endpoints are closed/disabled; the hidden display is stopped.
Raw observations, worlds, journals, credentials and detailed tick evidence remain
in ignored private storage. No commit, push, upload, release or deployment occurred.
