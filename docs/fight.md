# Simple per-mob fight policy — experimental SDK 0.2.0a6

Explicitly activate a bounded `fight` job. Nothing starts on launch/reconnect.
This is a small deterministic Python controller, not a model, a Java combat engine
or a persistent global settings switch. The existing alpha.3 mod primitives suffice;
no JAR replacement, transport change or extra world query is required.

MCP example:

```json
{
  "reactions": {
    "zombies": "fight",
    "skeletons": "fight",
    "spiders": "fight",
    "creeper": "evade"
  },
  "duration_seconds": 20.0,
  "min_health": 8.0,
  "radius": 8.0,
  "pursue": true,
  "melee_wait_seconds": 3.0,
  "allow_unarmed": false,
  "timeout_seconds": 30.0
}
```

Call `fight(...)` or `run_skill("fight", parameters)`, then `skill_status(job_id)`.
`cancel_skill` is cooperative; await terminal cleanup. `stop_inputs` and F8 remain
independent stop paths. Raw mutating tools reject competing control during the job.
Python: `player.fight(reactions={"zombies": "fight", "creeper": "evade"})`.

## Deliberately small rules

- Only exact IDs `minecraft:zombie`, `minecraft:skeleton`, `minecraft:spider` and
  `minecraft:creeper`. Other reported hostiles block; players are never selected.
  The policy is proximity response, not proof of which mob attacked first.
- Each key accepts `fight`, `evade` or `ignore`. Defaults are shown above. Any
  selected `evade` threat wins over fighting. Ignore means no proactive response
  to that type, not protection from it. Unknown keys/values fail before effects.
- Fight uses the **already selected** usable vanilla sword/axe. It never rearranges
  inventory, changes the hotbar, equips armor or consumes food. Explicit
  `allow_unarmed=true` permits an empty selected hand, not swinging arbitrary items.
  Sword attack attempts are spaced at least 0.7 s, axes 1.3 s, fists 0.5 s; a
  weapon change cannot shorten the prior spacing. Native cooldowns still own hits;
  sweeping/knockback may affect other entities, so this is not a friendly-fire guarantee.
- Face the reported eye position, allow a rendered refresh, recheck actor/health/
  target/policy, then require the exact native entity hit before an actor- and
  entity-fenced attack. A failed/timed-out native attack is not blindly retried.
- Visible zombies/skeletons/spiders beyond melee range may be approached using
  the existing loaded flat/full-block motor, hazard filtering and single-tick
  leases. `pursue=false` disables approach, not in-range attacks. When an enemy
  is out of reach with pursuit off, pursuit would cross a different level,
  or all still-known selected targets temporarily lose visibility,
  `melee_wait_seconds` (default 3, range 0–5) retains the job **without issuing
  movement** while waiting for a fresh in-range observation. Knockback can then
  resume melee within the same job, retaining the prior attack cooldown. Grace
  expiry returns the original blocked reason; zero restores immediate blocking.
  Target-ID switches do not reset a continuous wait. During visibility recovery,
  no look/drive/attack is requested; stale crosshair hits cannot authorize an
  invisible target. Recovery requires a fresh visible target and all normal
  attack gates. Evasion, health, actor,
  terrain, cancel and deadline checks still precede any attack. No jumping,
  swimming, stairs or terrain editing. Brief knockback loss of grounding releases controls and waits up to
  1.5 s; landing on a different level or prolonged airborne state blocks.
- Creeper fighting is explicit opt-in. Never chase a creeper; hit in reach only
  with a known escape available, then back off until reported distance reaches
  four blocks. A creeper closer than 1.5 blocks triggers retreat instead of a hit.
  There is **no fuse/charged-state prediction or explosion immunity**.
- At/below `min_health` (default 8 HP), no further attack is submitted after that
  observation. Attempt at most one short, known retreat pulse, then terminate.
  A retreat must increase distance from every reported threat and use a known
  hazard-free collision edge; otherwise stop. Fire, death, screens, world/player
  replacement and unsupported geometry stop the job. Damage above the threshold
  is tolerated only in this explicitly selected fight skill; autopilot's existing
  stop-on-damage policy is unchanged.
- Radius 1–8 bounds selected target distance and observed horizontal displacement
  from activation. Timeouts/duration are 0.1–120 s; the earlier deadline is checked
  by the combat loop and nested motion actions. Observation/physics/network delay
  can overshoot thresholds; they are not real-time distance or immunity bounds.

Progress reports behavior (`attack`, `approach_enemy`, `evade`,
`creeper_standoff`, `recover_grounding`), health and **attacks_submitted**.
`no_selected_enemies_observed` success means only absence from the bounded native
observation under the policy. A mob may have died, moved away or left the nearest
16 observations. No kill count is inferred (`kills_confirmed` is null when
included): neither disappearance nor an input receipt establishes a kill. An expired fight window is timed_out, not victory.

## SDK 0.2.0a5/a6 optimization

- Melee waiting above replaces external restart loops; it never projects a path
  onto unsupported terrain or extends the eight-block observation/radius.
- Keep sampling navigation/health/policy during cooldown. Prepare aim near its
  end instead of repeatedly looking, observing and querying inventory. Cached
  equipment information schedules preparation only: a fresh inventory check
  still gates every attack and pursuit pulse. The final guard uses the maximum
  current/prior weapon interval after rendered aim and fresh actor/target checks.
- Publish `attacks_submitted` immediately after a receipt, including across
  airborne recovery. `attack_wait_reason` distinguishes range, level, aim refresh,
  cooldown, target confirmation, crosshair mismatch and submission. Crosshair
  mismatch reports `crosshair_entity_id`; cooldown/wait durations are controller
  scheduling data, not measurements of native attack strength or immunity.
- In a deterministic six-attack fixed-target fixture, SDK a4→a5 inventory calls
  were 42→7, scene observations 21→6 and look calls 21→6. This is a **mocked
  primitive-count comparison**, not a real-client FPS/latency measurement. See
  [optimization evidence](evidence/fight-optimization.json).

## Qualification

**SDK a6 scoped live pass: finished an existing Normal zombie in one job.**
After reload, the job recovered visibility loss after attacks 1, 2 and 3, waited
for melee reach after knockback, and submitted four attacks without external
restarts. Sword wear rose 8→12; health stayed 19.33/20. New Rotten Flesh and an
Experience Orb appeared with the death animation, then the zombie disappeared
after 25 native ticks. See [live evidence](evidence/fight-visibility-live.json).

The target had already received two a5 attacks; its starting health was not
observed. This is a stationary continuation/finish, **not a fresh full-health,
group, Hard or general terrain qualification**. No invisible attacks or hidden
pursuit were added. FO11–FO14 cover repeated visibility recovery, bounded expiry,
stale crosshairs, evade priority and loss between aim and the final attack gate;
[component evidence](evidence/fight-visibility.json) remains separately scoped.

**Optimized SDK a5 live gameplay: PARTIAL.** After reload, one job waited for
melee reach and submitted one sword attack (wear 6→7), then blocked because no
selected enemy was visible. The player ended at 19.33/20 HP, paused. No new kill
was established; initial reach continuity is observed, but sustained knockback
continuity/single-job victory remain unverified. See
[live retest](evidence/fight-optimization-live.json). The earlier a4 kill below
does not qualify the new controller.
FO01–FO10 add deterministic one-job repeated-knockback, stationary level waits,
bounded grace/ID churn, cancellation and guard rechecks, equipment changes,
query budgets and immediate counters. These simulate observations, not Minecraft.

FC01–FC17 in `python/tests/test_fighting.py` cover per-type selection, policy
precedence/ignore, guarded aim and late native rejection, equipment/cooldowns,
pursuit/geometry, creeper back-off/no-chase, health boundaries, actor replacement,
knockback, strict schema, cancellation/deadlines/cleanup, MCP ownership and SDK
convenience. Fixtures simulate inputs and ray/AABB hits, not Minecraft combat.

**Prior SDK a4 scoped live pass: one Normal zombie, supervised wooden-sword melee.** Six
native sword attack submissions matched six durability points. Rotten Flesh
appeared alongside the target's death animation; after 25 native ticks the zombie
entity was gone and the loot remained. Final health was 17.17/20. See
[armed evidence](evidence/armed-zombie.json). The sword was crafted natively from
two harvested logs; no commands or spawning were used.

This required **eleven explicitly dispatched bounded melee jobs**, including
out-of-reach retries after knockback, not a single autonomous victory. Initial
pursuit was blocked by enemy_on_other_level. The generic skill still reports
kills_confirmed=null; this particular death was separately observed through loot,
death animation and subsequent entity disappearance. Armed Hard, skeleton,
spider, creeper, axe and group combat remain unverified. Unattended survival and
general terrain pursuit are not qualified.

**Earlier unarmed Normal/Hard trials: NOT ACCEPTED.** They demonstrated pursuit,
knockback recovery and health-limit termination but zero attack submissions.
Hard contact stopped at the health cutoff; Normal pursuit lost a target beyond
the bounded observation or stopped on the enemy-level guard. See the
[retained negative results](evidence/fight-maps.json), including an earlier Hard
fixture death outside an active fight job. A live test must use naturally encountered mobs
and real inventory/native actions, not summon/give, spawn eggs, world-file edits
or a damage-engine substitute. Use only disposable
owned fixtures or explicitly authorized worlds; preserve F8 and responsive cancel.
The installed SDK/tool was loaded by the MCP host for these trials. Frozen alpha.3
upload artifacts remain unchanged. Broader combat, ranged weapons, shields,
critical hits, equipment scoring, auto-eating and shelter construction are not part
of this minimal controller.
