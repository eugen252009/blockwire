# Movement-to-interaction pose handoff

This follows [replay baseline recovery](replay-baseline-recovery.md). Historical
QROT02, the grounding investigation and all failed recovery attempts retain
their original verdicts. This is a new qualification, not a reinterpretation of
old evidence. All experimental execution reuse is disabled throughout recovery.
See the [public evidence](evidence/pose-handoff.json) and its separate
[current-state hash manifest](evidence/pose-handoff-hashes.json). Private fixtures,
raw telemetry and source freezes remain excluded from distribution.

## Separate contracts

- **POSITION_REACHED:** the existing M0 target, arrival radius and safety checks
  hold. An ordinary M0 does not promise readiness for an arbitrary placement.
- **POSE_STABLE:** the existing native settling observations hold for an operation
  that requires them. A released key is not zero velocity. No stronger global M0
  radius, stationary threshold or consecutive-movement barrier is introduced.
- **INTERACTION_READY:** the supplied interaction's own fresh conditions hold.
  I3 still owns actor/source authority, ground/support, body clearance, the strict
  face plane, crouch reach, native hit identity and the placement postcondition.

A coarse accepted point need not satisfy I3. Conversely, an already stationary
invalid point cannot be repaired by waiting. `auto_position=False` never grants
positioning authority. `auto_position=True` authorizes the existing in-skill
positioning for one supplied target; it does not retry M0, insert BCL commands,
modify Q, or choose another building route.

## Native diagnosis

The historical QROT02 reconstruction matched **101/101 frozen files**. Its source
identity remains `663594efae7c3d1fe115962e84e7f527e5c438ec8b036c1c49d9bdbc67c55828`.
The previous authenticated hidden-display A/B demonstrated two complete reference
successes and the unfixed 41-block failure. Host/tick history is not completely
reconstructible; only observed causal claims are made.

New reduced traces bracket M0 completion, input cleanup, I3's first observation,
source navigation and native end-of-tick samples. Measured failing endpoints
were **already stationary**: positional drift over that handoff was exactly zero.
There is no evidence that a generic post-M0 delay repairs those failures. The
independent Sneak lease changed the earlier native pulse/coast trajectory, which
changed the settled endpoint accepted by the unchanged coarse M0 radius.

Two further real-client counterexamples distinguish the contracts:

1. On full support, precise Sneak positioning could release crouch together with
   its one-tick direction, restart at standing speed and oscillate around the
   unchanged 0.08 target. Edge-only stance retention did not cover this case.
2. A native sample already near an admissible interaction target could still be
   moving. Evaluating the interaction predicate *before* ordinary settling could
   provoke another directional pulse instead of observing the coast complete.

Private traces retain positions, velocity (including vertical), yaw/pitch,
collision/ground state, actual and remotely owned keys, actor identity, native
client/actor/game ticks, original typed action parameters and support geometry.
They are local evidence, not distributable recordings. First attributable input
transitions are distinguished from incidental earlier scheduling differences;
no universal first divergent tick is claimed.

## Correction

### Operation-scoped stance

Trusted internal `walk_to(..., pose_handoff=True)` requests a precision stance
handoff. Existing fine-radius movement also requests it. **Every walking radius
keeps the confirmed independent edge Sneak protection.** Ordinary full-support
navigation does not request the additional stance-observation gate. Direct motor
callers retain the existing edge-safe default. Neither option is a skill-schema
field or BCL opcode.

For explicitly requested Sneak precision, the shared motor prepares Sneak and
observes the native grounded crouch/eye state before submitting a direction.
Preparation is bounded to eight sampling opportunities and the existing task
deadline. Missing proof is `pose_stance_not_observed`, not success. Sampling
cadence is not a substitute for observing stance. Direction and Sneak use the
existing independently bounded native leases. Directional braking/release keeps
necessary authorized stance; ordinary task cleanup releases owned controls.

### One authorized local I3 preposition

If Q itself lacks robust partial support, I3 may select one local admissible
proxy only when its original `auto_position` authority and fresh source guards
permit it. The bounded selector considers one authoritative full-cube source,
the existing Q-proxy region and the supplied face/aim. It maximizes existing
geometric margins; its candidate spacing and score are not acceptance bounds.
A common support axis remains valid along the segment. It cannot invent source
authority, traverse unknown geometry or turn an invalid world into a valid pose.

The existing walker executes that one positioning goal with the unchanged 0.08
radius and an additional trusted arrival predicate. The order is:

1. Observe the existing destination radius.
2. Release directional input while preserving needed Sneak; perform the existing
   native velocity/position settling checks.
3. Evaluate the interaction's additional admissible-region predicate.
4. If still invalid, continue only the already authorized positioning operation;
   otherwise return. Existing stuck/deadline/cancel bounds remain in force.
5. I3 freshly rechecks actor, source authority, pose and reach. A walking receipt
   alone never authorizes use.

The Q proxy remains 0.35; robust contact remains 0.08 on both axes and 0.25 on one;
face clearance remains strictly greater than 0.05; crouch reach remains 4.5. No
arrival, grounding, face, contact, reach or placement verifier bound is relaxed.
A placement still requires the exact destination block and one-item consumption
from at most one use submission. No automatic action retry is introduced.

### Lifecycle and other interactions

No input-owner or key lease is transferred between M0 and I3 tasks. A child
positioning call uses the enclosing authorized skill context, actor fence and
cleanup. Actor/world replacement, cancellation, deadline, ownership rejection
and native transport failure terminate observation/control; transport loss is
terminal and is never reconnected/replayed.

Placement's four existing positioning call sites explicitly request handoff.
The mechanism is not house-specific: ordinary placement, recorded placement and
jump-placement preparation use the same walker. Existing approach/container
readiness already checks a fresh exact native hit and supported pose; mining,
removal and inspection retain their own guarded contracts. They are not silently
rerouted or made globally stationary by this change. Arbitrary shapes and new
interaction types remain outside this qualification.

## Attempts and honest negative evidence

All source copies, sealed fixtures, native exchanges and failed worlds remain
under ignored `build/pose-handoff-recovery/` with fresh attempt IDs.

| Candidate/cohort | Result |
| --- | --- |
| Preparation-only candidate / P01 | Local early/late/grounding passes; full ROT90 failed at 41 blocks. Not promoted. |
| Scoped edge policy / P02 | Full ROT90 GO, 71 blocks; not repeatability evidence. |
| Same source / S01 | First identity GO; second failed at 48 blocks during full-support precise positioning. Cohort stopped. |
| Observed full-support stance / P03 | Focused gates passed; full identity failed at three blocks at an already invalid I3 face pose. |
| Admissible local proxy / H07 | 15 positive focused goals and one correct no-auto negative; no ground loss. |
| Same source / P04 | Full identity failed at 41 blocks: interaction predicate preceded ordinary settling. |
| Correct ordering / H08 | Actual early and actual late counterexamples 3/3 each; grounding 1/1; no-auto negative 1/1. |
| Correct ordering / P05 | Full identity GO: 20/20 batches, 572 runtime operations, 71/71 placements and blocks, no failed actions/retries; native and closed-save PASS. |
| Same source / S04 | Four identity GOs retained. Stopped before transformations on safety code review: the coarse-radius edge-protection exception was not accepted. No new native fall is claimed. |
| Invariant-preserving correction / H09 | Original early/late and actual late prefixes 3/3 each; ordinary coarse edge walk 3/3; placement and no-auto negative PASS. The C5 coarse-walk control also succeeded. |
| Invariant-preserving correction / P06 | Full identity GO, 20/20, 572 operations, 71/71, no failure/retry, native and closed-save PASS. Edge protection retained at every radius. |

These cohorts are not pooled into repeatability or timing claims. Earlier
unfixed controls still fail the original early/late boundary. Full-support
precision controls can succeed in reduced runs; the original full failure is
timing-sensitive and is not presented as a deterministic reduced failure.

An investigation-only test-catalog edit invalidated one focused freeze before
the next client launch; the integrity gate rejected it with zero native actions.
Its results were retained and a fresh immutable cohort was used. Separate
pre-action launcher timeouts, including an observed Minecraft account-service
HTTP 429, are infrastructure failures, not gameplay attempts. Fresh attempts
followed an explicit cooldown; no game action was resumed or retried. Idle
launcher cleanup is same-user/hidden-display/owned-instance fenced and never
kills an active game or an unrelated launcher.

## Qualification status

- **Handoff:** invariant-preserving H09 gates, P06 full identity and frozen S05
  **9/9 PASS**.
- **Grounding:** corrected ordinary coarse edge walk 3/3 and placement PASS;
  original shared-movement functional regression **211/211 PASS**.
- **Standard replay:** P06 independently verified GO.
- **Repeatability:** S05 **GO, 4/4 independent identities**; C5 results are not
  pooled into C6.
- **Transformations:** S05 **GO, 9/9 standard cases**, with all reuse off;
  historical QROT02 remains unchanged.
- **Stateful optimization:** **NO-GO / DISABLED**, not tested for activation here.
- **Optimized production activation:** **NO-GO / DISABLED**.

S05 freezes nine independent attempts: four identities and ROT90/180/270, X01
translation and X03 reflection. Every attempt restores its canonical fixture;
all reuse flags are explicitly off. A failure stops the cohort. The original
49-scenario / 211-repetition native movement suite ran after S05 success.
The native movement regression completed **49 scenarios / 211 repetitions**, all
successful, using the existing native benchmark controller and closed-save
verification. No hidden-display timings are pooled with historical visible/GPU
measurements.

Automated final checks (also passed before S05): **597 Python tests**, Gradle `check`, **209/209 skill**,
**50/50 BCL**, **47/47 Play2Code** mutations and **10/10 TLS** checks PASS. Test
fixtures now model native Sneak/eye state and per-key lease expiry; existing
assertions and historical evidence are not weakened.

This does not establish H05 human generalization, arbitrary terrain, modpacks,
non-full-cube interactions or arbitrary rotations. All isolated clients, endpoints and the authenticated hidden display were closed;
configs are disabled. Physical F8 injection was not performed in this investigation;
its native implementation and existing contracts remain unchanged. No commit,
push, publication, release or deployment is authorized by these tests.
