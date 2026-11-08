# First open-ended autonomous Survival campaign

## Qualification

This is a real, bounded Minecraft campaign, **not H04/Test-A replay or a scripted
Survival progression**. The external LLM selected its objectives and generated
BCL from observed world feedback. There were no manual model replies, prepared
resources, teleports, Creative interactions or gameplay commands.

| Gate | Result |
| --- | --- |
| Campaign execution | **GO, scoped:** multiple independently verified native actions |
| Autonomous progress | **GO, scoped:** exploration, self-acquired timber, crafting and workshop placement |
| Basic Survival/home | **NOT QUALIFIED:** no shelter or established home |
| Long-term autonomy | **NOT QUALIFIED:** one short activation, no resume qualification |
| Normal/hostile-mob Survival | **NOT RUN:** Peaceful only |
| Replay capture | **GO:** original ReplayMod recording retained |
| Replay playback | **GO, scoped:** opened and played in actual native Replay Viewer |
| Recording integrity | **GO, scoped:** complete packet framing/CRC and expected bounded interval |
| Recording overhead | **NOT MEASURED:** no matched recorder-off control |

[Machine-readable evidence](evidence/autonomous-survival-campaign.json) and
[point-in-time hashes](evidence/autonomous-survival-campaign-hashes.json) keep these
verdicts separate. Earlier Survival, building and stateful evidence is untouched.

## World, model and architecture

- Minecraft **26.3**, Fabric, ordinary Default/noise world generation.
- New seed **74219031427**; world **Blockwire Survival Campaign 001**.
- Dedicated Prism instance **Blockwire-Survival-Campaign-001**; fresh native TLS
  identity, no copied accounts, certificates, credentials or worlds. Only selected
  instance launch metadata and existing mod JARs were reused.
- Survival, **Peaceful**, commands OFF, bonus chest OFF, empty initial inventory.
- Observed initial position **(-2.5, 90, 4.5)** in taiga; health/hunger **20/20**.
- Operator-selected persistent world namespace plus initial `level.dat` hash and
  private actor identity are recorded. The final closed save independently confirms
  seed, Survival, Peaceful and commands OFF. A world namespace is not a native UUID.
- Actual child UID/cwd/Java entrypoint/display were verified on authenticated hidden
  **`:99`** before the native connection. No unrelated game/launcher was running or
  terminated. No visible-session fallback.
- Model: **openai-codex / gpt-6.1-sol**, medium thinking, existing installed `pi` CLI
  through `CommandJSONDecider`, no model tools/extensions/context files. A format-only
  model-access probe succeeded before gameplay.

The primary instruction was the supplied short natural objective: survive,
establish a useful home and gradually develop the world; independently choose
resources, construction and priorities, observe results and do not invent success.
No wood→tools→house sequence or blueprint was supplied. Knowledge consisted of the
actual BCL command registry and the existing structured recipe catalogue.

The private qualification host is deliberately thin: external LLM → strict JSON/BCL
validation and durable `SessionStore` intent → authenticated loopback TLS
`BCLClient` → existing `BCLGateway`/`BCLJobs`/`AgentRuntime` → native player → fresh
BCL observations. There is no new player controller or alternate execution stack.
Persistent memory is model-authored data; validation/budgets are host responsibilities,
not a planner. Production Python/Java sources are unchanged from `a9a7405`.

Exposed operations: M0/M1/M2, C0–C3, I0–I4, V0–V2, S0–S4. Combat, event programs,
evidence-only recorded-path adapters, commands and unsupported invented opcodes
were not authorized. Crafting recipes, placement shapes and terrain remain bounded
by the existing implementation. Storage transfer, farming/growth/smelting and
arbitrary terrain are not implied capabilities. No Combat subsystem was changed.

## Bounds and actual autonomous decisions

Prospective limits: **30 model decisions, 300 compiled/submitted BCL operations,
30 minutes**, at most 24 operations per model frame, eight failed frames/decisions
and two identical failed-frame submissions. Model calls were bounded at 150 seconds;
existing runtime action budgets remained authoritative. Each decision reserved fresh
V0/I0 follow-up observations; durable pending intent preceded submission. Uncertain
transport would stop without reconnect/replay.

Actual activation: **12 model decisions**, **80 compiled/submitted operations**,
about **498.212 seconds** from the pre-action recording check to terminal result.
There were **62 returned skill outcomes: 54 succeeded, eight blocked**. The 80 is
budget accounting, **not a claim that every operation after an aborted frame ran**.

The model's actual choices, preserved verbatim with generated BCL privately:

1. Choose nearby spruce timber as a useful resource.
2. Reposition after no reachable exposed logs were found.
3. Try newly exposed wood; receive a mining timeout.
4. Choose a more offset stance and successfully gather one log.
5. Choose and craft four spruce planks and a crafting table; later timber harvesting
   in that same frame fails. Successful crafting is not erased by the blocked frame.
6. Try another observed stance, then abandon that trunk after another timeout.
7. Explore another supported area rather than repeatedly inspect unchanged terrain.
8–10. Select other spruce trunks/approaches; observe reach and mining failures.
11. Choose a small workshop site and place the crafted workbench with I4.
12. Revise the near-term project toward a soil shelter and try gathering an exposed
    grass block. Mining remains unobserved; the eighth failed frame ends the run.

This sequence was **not supplied in advance**. Actual source frames, model requests,
replies, compiler/runtime responses and native audit are under the ignored
`build/autonomous-survival/campaign-001/`. Public evidence records decision notes and
source hashes, not private raw world/identity traces. Model notes are not acceptance.

## Independent results and failures

Closed native statistics confirm exactly:

- **One spruce log** mined and picked up.
- **Four spruce planks and one crafting table** crafted.
- **One crafting table** used/placed.

A separate read-only region audit confirms `minecraft:crafting_table` at
**(15, 88, 15)**. Eight native walk operations returned observed arrival. Final saved
position is approximately **(16.646, 88, 12.350)**; health/hunger **20/20**, empty
inventory. The consumed log→planks→table→placed-table chain is consistent with saved
statistics and the physical voxel, not merely receipts or model claims.

**No shelter, home, tools, stone collection, food production or storage system was
established.** Peaceful full health/hunger is not hostile-mob or sustainable food
qualification. No kill, death-recovery, safety-immunity or long-term claim is made.

Failures were **two `no_reachable_exposed_logs`** results and **six
`mining_not_observed`** timeouts (five wood, one soil). These are resource-access
rejection and mining postcondition failures, not invalid BCL, fabricated success,
transport failure or an automatically retried use. Model-selected subsequent
attempts after changed observations/stances are visible in the original trace.
The exact native mining cause is **not established**; repeated failures were not
hidden or "fixed" by weaker reach/contact/settlement checks.

The old benchmark region decoder rejected the fresh 26.3 empty-key block-palette
serialization. It was not modified and no historical verdict was reinterpreted.
A narrowly scoped private audit decoded the one requested workbench voxel with
strict coordinate/section/bit-index and exact palette-entry checks. Final native
placement evidence and saved item/statistics supply independent corroboration.
Earlier UI selection, replay-staging-path and audit diagnostic errors are retained;
none restarted or reset gameplay.

## Replay recording and owner playback

ReplayMod **26.3-2.6.28** was obtained from its Modrinth project after verifying
upstream ReplayMod ownership, exact Minecraft/Fabric compatibility and download
SHA-512. Flashback compatibility was also queried, but was not installed alongside
ReplayMod. The original test instances were not modified. No streaming or editing
integration was added; Play2Code remains independent.

Before the campaign, a separate natural-world smoke session produced a recording
that was opened and played in the actual Replay Viewer. During the campaign,
auto-recording started at world join before any autonomous BCL action. A recording
staging directory was present before execution; a growing actual `recording.tmcpr`
stream was checked during gameplay. The first staging-directory size was **not**
a finalized replay-file size. After all agent actions stopped, normal save/quit and
the recorder's Done confirmation finalized the original recording.

**Owner artifact:**

`build/autonomous-survival/campaign-001/replay/session.mcpr`

- Original unmodified copy: **8,382,961 bytes**.
- SHA-256: `2c13c2912fe355d0f3b1480e2446e2da4c1e1fca38ff8f57bec9ee0001d7279d`.
- **230,260 packets**, first timestamp **6 ms**, last **499,816 ms**.
- ZIP CRCs and complete monotonic packet framing pass.
- Native viewer lists **08:19**, matching the bounded active interval. Recording
  began during world creation; paused setup is not equivalent to wall-clock video
  duration. The pause-adjusted stream spans the 498.212-second agent interval and
  normal shutdown margin; no unexplained truncation was found.

The same original campaign archive was selected, opened and played in the real
viewer, with early/later terrain/camera views, recorded-player overview and a
recipe-unlock toast observed. This is more than a nonempty-file check. **Not every
mining, placement or inventory GUI interaction was visually audited**; frame-by-frame
visual completeness and cinematic rendering are not qualified. ReplayMod's
free-camera/spectator controls are available; no reconstructed BCL video was used.

To watch locally: launch **Blockwire-Survival-Campaign-001** in Prism, leave Blockwire
control disabled, open its **Replay Viewer** title-screen button, and select
**2026_11_04_08_00_05 — Blockwire Survival Campaign 001**. The original also remains
in that instance's `replay_recordings/`. The ignored build copy is separately
preserved; do not upload it or package the world/account data with a distribution.
Recording performance overhead remains **NOT MEASURED** without a matched control.

## Persistence, shutdown and QA

The original world was saved, **never reset after failures**, and remains in the
new instance for future play. A separately hashed final closed snapshot is retained.
`campaign.sqlite` stores the natural objective, model memory, project/known locations,
home=null, progress, failures, pending work, actor binding and counters. The model's
last remembered pose can be stale after the final failed operation; fresh final
native/saved state remains authoritative. There is no pending effect to replay.
A future activation must explicitly rebind the new actor and revalidate memory;
automatic restart/resume and multi-session reliability were **not tested**.

Agent submission stopped at the failure boundary; existing runtime cleanup released
owned controls, normal native save/quit preserved the world, the replay was finalized
and inspected, and the client then exited normally. Gateway/client processes and
ports **8765/8879** are closed, instance control disabled, hidden display stopped.
Unrelated processes were untouched. Experimental stateful options remain off.

Final checks: **603/603 Python**, Gradle check, **209/209 skill**, **50/50 BCL**,
**47/47 Play2Code** mutations and **TLS 10/10 PASS**. No production source change
required a new 211-case movement qualification. Physical F8 injection was **NOT RUN**;
implementation/contracts remain unchanged. No commit/push/tag/upload/release/deploy.

## Next improvements, not hidden recovery steps

Investigate the retained native mining/reach/lease/postcondition traces before
claiming a general mining fix. Improve structured feedback so a model can distinguish
unreachable wood, a hit that never completed mining and an unavailable drop. Test
new independently chosen acquisition strategies and explicitly resumed memory on
this same preserved world. A safe home, tools and longer Peaceful operation remain
future gameplay objectives, not a prewritten campaign script or claimed achievements.
