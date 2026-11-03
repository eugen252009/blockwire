# Shared native-feedback motion motor (experimental)

`python/src/blockwire/skills/motion.py` supplies the movement motor used by
`walk_to`, `approach` and ordinary autopilot travel. MCP/BCL supplies goals; the
existing Python worker plans over explicit client-known observations and sends
ordinary actor-fenced native look/drive/jump inputs. Minecraft owns acceleration,
collision, jumping, falling and damage.

There is no neural movement model, teleport, velocity setter, parallel MCP
steering stream, benchmark-only controller or Python collision simulator.

## Operation-scoped pose handoff

[Pose handoff](pose-handoff.md) is a trusted in-skill request, not a BCL setting
or a globally stricter M0 destination. Ordinary navigation retains its qualified
pulse/lease behavior. Explicit fine Sneak positioning observes native crouch
before direction and retains bounded authorized stance through directional
release; cleanup still releases it. An interaction may add a strict boolean
arrival predicate after the existing radius and native settling observations.
This does not add a second controller or transfer task/key ownership. I3's fresh
geometry and exact native placement postconditions remain authoritative.

## Observed route model

The native client exposes bounded local geometry rather than arbitrary world
queries:

- `flat_full_blocks_v1`: at most 81 loaded same-height full-block cells;
- `stepped_full_blocks_v1`: at most 405 loaded cells, Y ±2;
- typed `flat`, `diagonal`, `step` and `gap_jump` transitions;
- velocity, horizontal speed, collision flags, grounded/sprint/sneak state and
  the actor session alongside the mesh.

Same-height diagonals require both corner-adjacent cells and a clear native body
sweep. One-block axial steps require a conservative clearance envelope. A gap
transition is considered only for a bounded two-cell axial/diagonal gap with an
absent middle cell, clear flight envelope, proven run-up cell and broad landing
support. Unsupported or untyped long edges fail as `unsupported_route_edge`.

When a grounded body is partially supported and its position cell has no usable
centre (the roof-overhang case), native code may select one nearby same-height
supported source cell. This recovery is distance bounded, requires actual native
collision clearance and is reported explicitly; it is not a teleport or a claim
that the target is reachable.

Python routing uses geometric edge cost. Equal-cost paths retain native discovery
order. This prevents diagonal edges from being treated as free compared with
cardinal edges and removes long-axis weaving while preserving obstacle detours.
Unknown/unloaded space is never invented.

## Motor behavior

- The desired world vector is quantized into ordinary W/A/S/D combinations while
  one native actor-bound camera plan follows the shortest yaw arc over real elapsed
  client-tick time. The motor refreshes the observed view before quantization.
  Turn/drive overlap is allowed only with freshly proven broad lateral support;
  narrow or uncertain support stops and replans before movement.
- Safe travel can retain a 1–8 tick native input lease across observation and
  steering cycles. Every renewal follows cancellation/deadline and actor checks;
  a stalled Python worker cannot renew past the native expiry. Natural movement
  lease expiry releases keys without cancelling an independent camera plan;
  explicit global stop/F8 still cancels both.
- Collinear flat/diagonal routes may look ahead at most four observed edges. The
  motor never shortcuts an unknown corner, step or gap.
- Observed horizontal speed contributes to braking distance. Sudden implausible
  observed speed growth releases input instead of blindly renewing it.
- Short or uncertain stages use one- or two-tick precision actions. Ordinary
  walking remains upright unless sneak was explicitly requested; damage avoidance
  does not silently enable crouching.
- A one-block step is executed in a separate bounded loop. The transition is
  reobserved before input, ascent jumps once, descent releases before the centre,
  and landing must be observed inside progress/height/lateral envelopes.
- A proven gap uses a separate bounded native-jump loop. Long/diagonal gaps may
  start from exactly one proven run-up cell. Jump is released while descending to
  avoid an extra landing hop. Actor replacement, cancellation, damage, changed
  geometry, lateral escape or an unverified landing stops the action.
- An observed hazard-free landing in the intended cell, or in one adjacent broad
  supported cell near the end of the jump, may return to normal replanning. This
  is not arrival; the caller still has to observe the goal postcondition.

`avoid_damage` filters known local hazards/hostiles and stops on observed health
loss. It is best effort, not immunity: client knowledge can be incomplete and
native physics remains authoritative.

## Arrival and ownership

Ordinary `walk_to` retains its 0.3-block radius. Placement adapters may request
0.08–0.3 through `arrival_radius`. Every radius now requires all of the following:

1. native position is inside the requested horizontal radius and vertical bound;
2. owned movement input has been released;
3. observed horizontal speed is at most 0.004;
4. a second native position sample changes by at most 0.005 m.

A drive receipt, expired lease or skill-level `arrived` is never sufficient by
itself. Independent benchmark acceptance uses the settled telemetry position.

The activation-bound `actor_session` is passed to every look/drive and checked in
all loops. Existing health/readiness, cancellation/deadline, single-owner cleanup,
F8 stop and native input expiry remain in force. Cleanup always attempts to
release owned controls; uncertain cleanup is not success.

Progress fields such as `control_mode` and `owned_input_lease` describe controller
intent, not an observed gameplay outcome. `steps` counts feedback updates rather
than blocks or completed key pulses.

### Validated local edge-pose crouch lifetime

A supported local edge pose uses the existing bounded Sneak motor, not a new
route or collision model. Crouch must already be active during preparation and
must not expire with its one-tick directional pulse: native residual velocity can
otherwise slide the player off the support after key-up. Python now uses the
existing per-button lease contract to keep crouch bounded to eight ticks while
retaining a one-tick direction, then keeps crouch during observed settlement.
Actor loss, deadline, cancellation and ordinary skill cleanup still release input.
The support/contact, arrival-radius and velocity thresholds are unchanged.

This correction passed the focused native edge-placement reproduction. It does
not establish full replay success: current pilots also expose a separate mismatch
between coarse M0 arrivals and the next placement's robust pose requirements.
See [stateful-input-execution.md](stateful-input-execution.md) for the independent
component and full-replay verdicts.

### Sealed Play2Code recorded paths

Play2Code M3/M4/M5 replay is a separate evidence-bound adapter, not ordinary route
planning. It can submit only sealed one-tick direction samples, with at most three
pulses per sample and only bounded passive native-coast observations afterward.
For M4, a directional sample immediately followed by a hold sample is considered
already complete only when both recorded targets are inside the unchanged arrival
radius. Otherwise the adapter may apply only that directional sample's recorded
pulse. This prevents a reachable penultimate target from stranding an unreachable
hold target that cannot emit movement. It adds no retry, tolerance, synthesized
control or alternate path; actor, deadline, cancellation, lease and cleanup fences
precede every action and remain active in the loop. The confirmed ROT180 case and
QROT02 qualification are documented in
[play2code.md](play2code.md#rot180-stabilization--root-cause-confirmed-qrot02-repeatability-go).

## Native telemetry

`MotionTrace` is a bounded 4,096-sample end-of-client-tick ring. The optional,
actor-fenced `motion_trace` RPC reports:

- client/actor/game tick and monotonic identifiers;
- position, velocity and horizontal speed;
- yaw/pitch and bounding box;
- horizontal/minor/vertical collision and grounded state;
- sprint, sneak, health and fall distance;
- actual native inputs and remotely owned inputs.

The deterministic benchmark writes one CSV and JSON result per repetition. No
canonical native/before/after run dropped a trace sample.

## Qualification

The fixed Minecraft 26.3 movement benchmark is documented in
[movement-benchmark.md](movement-benchmark.md). On the identical 49-scenario,
211-repetition cohort:

- native reference: 211/211;
- preserved pre-optimization controller: 176/211;
- final controller: 211/211.

Against the preserved controller, aggregate ticks fell 47.6%, full-stop runs
89.3% and input changes 68.0%. Strict native tick parity remains NO-GO: the final
controller uses 20.5% more aggregate ticks than the reference, principally on the
multi-level platform route.

That historical movement qualification included 440 Python tests, Gradle
contracts, ten real TLS interoperability checks and 227/227 killed applicable
mutations. Machine-readable evidence is
[evidence/movement-benchmark.json](evidence/movement-benchmark.json).

After native timed rotation was integrated, the unchanged 211-repetition cohort
was rerun as `after-rotation-v4`: **211/211**, 17,908 total ticks, median 70,
maximum error 0.290098 m, zero health loss and zero dropped samples. Rotation and
the fresh 71-block construction regression have separate gates in
[rotation-benchmark.md](rotation-benchmark.md).

Earlier continuous-motion component evidence and the first two-leg live trial
remain historical in [evidence/continuous-motion.json](evidence/continuous-motion.json)
and [evidence/walk-continuous-live.json](evidence/walk-continuous-live.json). Their
older counts and narrower claims are not the final movement qualification.

## Limits

The supported observations are conservative full-block mechanics, not general
Minecraft navigation. Slabs, fluids, caves, arbitrary collision shapes,
unknown-height long routes and general chunk exploration remain unsupported.
Continuity still depends on feedback arriving before native lease expiry; slow
rendering or networking deliberately causes a safe stop rather than an unbounded
hold. Hostile, food-constrained and unattended Survival reliability is not
established by the deterministic fixture.
