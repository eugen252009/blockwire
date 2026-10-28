# Shared continuous-feedback motor (experimental)

`python/src/blockwire/skills/motion.py` supplies the motor used by `approach` and
ordinary `autopilot` travel. MCP supplies goals; the Python worker performs the
feedback loop. No neural network, parallel MCP steering requests, new wire RPC
or Java physics/controller is involved. `walk_to` is unchanged.

## Construction and bounds

- Roll only along at least two consecutive, collinear cardinal edges from the
  current loaded, native collision-validated flat-ground route. Look ahead at
  most four edges; never shortcut a corner or an unknown connection. Start near
  the route axis (lateral offset at most 0.06 blocks).
- Face the travel direction and hold W (with the selected sneak/sprint policy).
  While rolling, keep input owned during navigation/scene observations and small
  camera corrections. Renew using the existing actor-fenced `drive`; do not
  send an explicit stop between feedback updates. Native replacement of a hold happens
  on the game thread, without a Python-induced idle physics stage.
- Each rolling request is **4–8 ticks (200–400 ms)**, replacing the old motor's
  wait-for-expiry sequence on eligible straight segments. Revalidate after a
  cooperative 50 ms wait plus observation/network time before any renewal. A
  shorter available corridor, mode/direction change or camera correction over
  four degrees relative to the observed view releases input before turning.
- A remaining-distance budget reserves 0.6 blocks and uses the larger of 2.5×
  nominal per-tick speed and 1.5× the highest observed per-tick speed estimate.
  This is a conservative **heuristic**, not an authoritative physics/speed bound.
  Server corrections, momentum, buffs, human input and other mods can invalidate
  it. Native collision and damage remain entirely Minecraft's responsibility.
- Short segments/final positioning use stopped precision pulses: one tick under
  0.35 blocks from the chosen waypoint, otherwise the caller's short pulse cap
  (approach: three ticks). No drive is added during large alignment turns.
- Preserve approach's **eight unconfirmed movement updates / three cooperative
  seconds** target-checkpoint budget. Every rolling renewal counts; continuously
  holding W does not grant unlimited target memory. Checkpoints release input.
- Creeper evasion retains its immediate stopped facing/short-pulse policy, rather
  than delaying emergency response for gradual travel alignment. Defense and
  behavior transitions release prior movement. Autopilot re-observes arrival
  after releasing a still-owned rolling lease before returning success.

The same activation-bound `actor_session` goes to every look/drive. Existing
health/hazard/readiness, cancellation/deadline, single-job ownership, final
cleanup, F8 and native expiry checks remain. A stalled controller cannot renew;
its last requested rolling hold is at most 400 ms, subject to game-thread progress.
Native protocol limits remain 100 ticks / five seconds. No automatic restart.

## Observability and qualification

Progress includes `control_mode` (`stopped`, `turning`, `rolling`, `precision`) and
`owned_input_lease`. These describe controller intent/ownership bookkeeping,
**not observed native key state, velocity or a gameplay outcome**. `steps` counts
movement feedback updates, not completed disjoint pulses, so historical counts
are not performance comparisons.

`python/tests/test_continuous_motion.py` covers CM01–CM13: precision centering,
held-input overlap during observations/look/renewal, expiry without renewal,
large-turn release, uncertain geometry/readiness/actor change, cancellation,
damage/deadline, post-release arrival, bounded collinear lookahead including four
cardinal directions, observed-speed changes, both skill integrations and failed
cleanup. Small advances accumulate across feedback samples rather than falsely
triggering the old per-pulse stationary threshold. The shared fixture advances motion with elapsed lease time, rather than
instantly applying each requested lease's entire duration. It does not reproduce
Minecraft friction, collision shapes, tick scheduling or networking.

Component checks: 82 Python tests, 43 killed isolated skill mutations, Gradle check
and ten real Netty/Python TLS interoperability checks. See
[evidence](evidence/continuous-motion.json); logs are under
`build/continuous-motion-verification/`.

**Live/isolated graphical acceptance of this motor: NOT RUN.** Continuity depends
on feedback arriving before native expiry; slow rendering/networking can still
produce gaps, deliberately failing safe instead of extending holds blindly.
Smoothness, terrain safety and actual gameplay are not established by fixtures.
No player movement, menu opening or inventory operation was requested during this
implementation. Reload the Python/MCP host before a separately authorized test;
this change requires no new Minecraft JAR.
