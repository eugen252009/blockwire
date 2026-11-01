# Blockwire – konsolidierte Entwicklungs- und Änderungshistorie

Diese Datei beschreibt zusammenhängend, **wie sich die aktuelle qualifizierte
Arbeitskopie entwickelt hat**, welche technischen Änderungen vorgenommen wurden,
welche Fehlversuche erhalten blieben und welche Aussagen durch echte
Minecraft-Evidenz gedeckt sind.

Sie ersetzt keine der fachlich engeren Spezifikationen. Maßgeblich bleiben:

- [Architektur](architecture.md)
- [Protokoll](protocol.md)
- [Skills](skills.md)
- [BCL/1](bcl.md)
- [Persistent Projects](projects.md)
- [Superflat-Benchmark](superflat-building.md)
- [Movement-Benchmark](movement-benchmark.md)
- [Rotation-Benchmark](rotation-benchmark.md)
- [maschinenlesbare Rotation-/Regressions-Evidenz](evidence/rotation-benchmark.json)

Private Zertifikate, API-Schlüssel, Journale, Snapshots, Saves und rohe
Modellantworten gehören **nicht** zu dieser Dokumentation und dürfen nicht in ein
Distributionspaket aufgenommen werden.

---

## 1. Ausgangspunkt und unveränderte Systemgrenzen

Blockwire verwendet weiterhin genau einen Ausführungsstack:

```text
externes Modell oder lokales Programm
    -> BCL/1 beziehungsweise typisierte Python-Ziele
    -> bestehende Registry und Skill-Laufzeit
    -> Player/Backend
    -> authentifizierte TLS-WebSocket-Verbindung
    -> native Minecraft-Aktionen
    -> Minecraft-Physik und beobachtete Postconditions
```

Die Entwicklung hat **keinen zweiten Bewegungs-, Bau- oder Rotationscontroller**
eingeführt. Unverändert gelten insbesondere:

- TLS ist obligatorisch; es gibt keinen Klartext- oder Trust-all-Fallback.
- Jede Instanz besitzt eine separat vertraute Zertifikatsidentität.
- API-Key, Hostname-Prüfung, Loopback-Defaults und Verbindungsgrenzen bleiben
  erhalten.
- F8 beziehungsweise explizites Stoppen gibt native Eingaben frei.
- Spieler- und Weltwechsel werden mit `actor_session` eingezäunt.
- Native Minecraft-Logik besitzt Bewegung, Kollision, Schaden, Sprung, Crafting,
  Inventaränderungen und Platzierungsergebnisse.
- Ein RPC-Receipt ist kein Gameplay-Erfolg.
- Erfolg setzt eine beobachtete Ziel-Postcondition voraus.
- Unsichere Effekte werden nicht blind wiederholt.
- Abbruch- und Deadline-Prüfungen erfolgen vor Aktionen und innerhalb langer
  Schleifen.
- Fehlversuche, Debug-Fortsetzungen und Recovery-Probes werden nicht nachträglich
  als frische Erfolge umetikettiert.

Diese Grenzen waren die Leitplanken für alle nachfolgenden Änderungen.

---

## 2. Frühere Grundlage: native Aktionen, Skills und Survival-Mechanik

Die erste Entwicklungsphase etablierte den allgemeinen Actor-Stack:

- `Player(Backend)` als kleine programmierbare Actor-API;
- gepinnte native TLS-Verbindung;
- bounded Observation-, Inventar-, Menü- und Eingabeoperationen;
- Skill-Registry, Ausführung, Ownership, Status und kooperative Cancellation;
- native Input-Leases statt unbeschränkter Tastendrücke;
- konservative Sicht-, Terrain- und Gefahrenbeobachtungen;
- Crafting, Equipment, Nahrung, Mining, Placement und UI-Fencing mit
  beobachteten Postconditions.

Darauf entstanden die Survival- und Stone-Age-Versuche. Der erhaltene echte
Tool-free-Erfolg `attempt08` verwendete `openai-codex / gpt-6.1-sol` und erreichte
nach 26 Entscheidungen unter anderem:

- 18 Cobblestone als beobachteten Peak;
- eine Stone Pickaxe;
- 20 Gesundheit;
- `objective_verified: true`.

Dieser Erfolg ist kein Nachweis für vollständiges, unbeaufsichtigtes Survival.
Andere Versuche und nicht inspizierte Artefakte – insbesondere `attempt09` –
bleiben separat und werden nicht in diese Aussage einbezogen.

---

## 3. BCL/1: Compiler, typisierte IR und Gateway

Die nächste Phase führte BCL/1 als kompakte, aber vollständig validierte
Steuerungssprache oberhalb derselben Skills ein.

### 3.1 Compiler- und Laufzeitgrenzen

Implementiert wurden:

- vollständige Frame-Validierung **vor** dem ersten Effekt;
- deterministische Kompilierung in eine eingefrorene typisierte IR;
- deklarativ aus Skill-Schemas erzeugte Command-Metadaten;
- modale Session-Zustände;
- FIFO-Jobs und Events;
- persistente Request-Deduplikation;
- getrennte Bedeutungen von `program_verified` und `objective_verified`;
- strukturierte Compilerdiagnosen ohne `eval`, `exec` oder implizite Ausführung;
- keine Rollback-Versprechen und kein Replay unsicherer Effekte.

`program_verified` bestätigt nur die Postconditions der ausgeführten BCL-
Operationen. Es bestätigt **nicht** automatisch das externe Gesamtziel.

### 3.2 Gateway-Härtung

Das optionale Python-Gateway erhielt zusätzlich:

- getrennte Controller- und Observer-Rollen;
- eine Actor-Bindung bis zum bestätigten Cleanup;
- bounded Queues und sichtbare Overflow-Fehler;
- Quarantäne-/Reaper-Logik für verspätetes Cleanup;
- typisierte Lifecycle-Events E104–E107;
- explizit eingezäuntes Respawn;
- responsive Status-/Cancel-Operationen trotz laufender Jobs.

Das Gateway ist kein zweiter Planner. Es kompiliert und dispatcht weiterhin in
die bestehende Runtime.

---

## 4. Persistent Projects und externe Planung

Mit `projects.py`, `project_agent.py` und `project_inspection.py` kam eine
persistente Projektlage hinzu. Sie trennt:

- den vom Modell verfassten Plan;
- noch ausstehende Intents;
- terminale Operationen;
- beobachtete Blockzustände;
- native Zugangsgeometrie;
- die unabhängige Zielverifikation.

Wesentliche Sicherheitsregeln:

- verlorene Acknowledgements dürfen keine Effektwiederholung erzwingen;
- alte Beobachtungen werden nach Actor-/Weltwechsel nicht als frisch behandelt;
- ein Modell-Finish ist kein objektiver Erfolg;
- Materialarithmetik beschreibt Bedarf, ist aber keine Bau- oder
  Progressionsstrategie;
- Read-only-Verifikation erhält keine mutierenden Rechte.

Erhaltene Ergebnisse umfassen unter anderem:

- A01: 56 Calls, 40 Platzierungen, 43/43 akzeptierte Schritte;
- A02/A03: keine doppelte Lost-ack-Ausführung, aber fehlgeschlagener Dachabstieg;
- B03: sechs Logs gesammelt, 24 Planks hergestellt und Struktur gebaut, danach
  `OBJECTIVE_INCOMPLETE / no_relevant_progress_budget`;
- B04: Operationslimit 512;
- B07: 26/26 Read-only-Prüfungen;
- B08: `OBJECTIVE_VERIFIED`.

Diese Projektresultate sind jeweils auf ihren eigenen Scope begrenzt.

---

## 5. Deterministischer 5×5-Superflat-Benchmark

### 5.1 Fixture und Akzeptanz

Der Bau-Benchmark verwendet ein byte-identifiziertes Minecraft-26.3-Snapshot:

- Seed `31052026`;
- Ursprung `(0, -60, 0)`;
- Start `[2.5, -60.0, -3.5]`;
- 46 Wandblöcke;
- 25 Dachblöcke;
- insgesamt 71 erforderliche Cobblestone-Blöcke.

Die Akzeptanz prüft unabhängig:

- alle erforderlichen Blöcke;
- falsche, fehlende und unbekannte Zustände;
- literal freie Eingang-/Innenräume;
- vollständiges Dach;
- intakten Boden;
- keine zurückgelassenen Hilfsblöcke;
- nativen Zugang;
- einen sicheren finalen Spielerzustand.

Jeder frische Lauf restauriert dasselbe geschlossene und byte-verifizierte
Snapshot. Administrative Commands dienen nur dem Fixture-Setup und zählen nicht
als Bauleistung.

### 5.2 Generische Korrekturen während der Entwicklung

Die Bauversuche führten zu wiederverwendbaren Mechanikverbesserungen:

- frische Same-height-Pickup-Recovery;
- präzisere, stabil beobachtete Ankunft;
- exakte `GatherBlock.position`-Filterung;
- generisches `remove_block`/C3;
- vollständiger Actor-Bracket-Nachweis für finale Zugangsprüfung;
- Prüfung des gesamten möglichen 0,15-Block-Ankunftsintervalls bei Placement;
- konservative Reichweiten- und Body-Margins;
- keine spezielle Hauslogik und kein nativer House-Generator.

A01–A10 bleiben als Kalibrierungsfehler erhalten, darunter Deadline-, Reach-,
Inventory-, Speicher- und Startup-Probleme.

### 5.3 Eingefrorene Entscheidungen

Die unveränderte Test-A-Kohorte A11–A13 bestand 3/3:

- 71/71 erforderliche Blöcke;
- je 288 ausgeführte Skills;
- je 82 verifizierte Placement-Events;
- keine fehlgeschlagenen Aktionen;
- alle unabhängigen Sicherheits- und Zugangsprädikate erfüllt.

Damit bleibt **Test A: GO**.

Der echte externe Modelllauf B01 baute zwar 71/71 erforderliche Blöcke, hinterließ
aber sechs Hilfsblöcke und keinen gültigen finalen nativen Zugang. Er endete mit
`no_relevant_progress_budget`. Damit bleibt **Test B: NO-GO**.

F01–F03 und R02 qualifizieren nur Fault-/Recovery-Verhalten. Sie sind keine
vollständigen Häuserfolge.

---

## 6. Movement-Optimierung und native Tick-Telemetrie

### 6.1 Messinfrastruktur

`MotionTrace.java` führte einen bounded Ringpuffer mit 4096 End-of-client-tick-
Samples ein. Er enthält unter anderem:

- Position und Geschwindigkeit;
- horizontale Geschwindigkeit;
- Yaw/Pitch;
- Kollisionen und Ground-State;
- Bounding Box;
- Sprint/Sneak/Fall/Health;
- tatsächliche und remote besessene Inputs;
- Actor-, Game- und monotone Zeitidentitäten.

Der deterministische Movement-Benchmark enthält 49 Szenarien und 211
Wiederholungen für lineare, diagonale, vertikale, kombinierte, Kurven-,
Parkour-, Dach- und Präzisionsfälle.

### 6.2 Controller-Änderungen

Die generischen Movement-Verbesserungen umfassten:

- konservative same-height Diagonalen;
- typisierte `flat`, `diagonal`, `step` und `gap_jump`-Transitions;
- geometrische Dijkstra-Kosten statt gleicher Edge-Kosten;
- deterministische Tie-Breaks;
- W/A/S/D-Quantisierung mit kurzen nativen Leases;
- Braking aus beobachteter Geschwindigkeit;
- getrennte bounded Step- und Gap-Schleifen;
- nachgewiesene Run-up-/Landing-Geometrie;
- konservative Replanung nur von beobachtet sicheren Landungen;
- stabile Ankunft erst bei `horizontal_speed <= 0.004` und zweitem Sample mit
  maximal 0,005 m Positionsänderung.

### 6.3 Iterative Kohorten

Die Entwicklung wurde nicht auf den letzten Erfolg reduziert:

- `after-v1`: 208/211; drei erhaltene `step_x_descend`-Fehler;
- `after-v2`: 210/211; ein Level-4-Plattformfehler;
- gezielter Level-4-Follow-up: 3/3;
- `after-v3`: 211/211;
- `after-v4`: 211/211 als historische finale Movement-Kohorte.

Verglichen mit dem ursprünglichen Controller:

- Erfolgsquote +16,6 Prozentpunkte;
- Ticks −47,6 %;
- Full-stop-Runs −89,3 %;
- Inputwechsel −68,0 %.

Die strikte native Performance-Parität blieb **NO-GO**, weil Blockwire insgesamt
20,5 % mehr Ticks als die native Referenz benötigte. Der Level-4-Plattformweg war
der größte verbleibende Abstand.

---

## 7. Migration von festen 8°-Schritten zu nativer zeitbasierter Rotation

Dieser Abschnitt beschreibt die jüngste Entwicklung im Detail.

### 7.1 Ausgangsproblem

Normale Nicht-Kampf-Kamerabewegungen wurden zuvor in Python in festen 8°-Schritten
ausgeführt. Dadurch hing die reale Dauer primär vom Winkel und von RPC-/Update-
Raten ab, nicht von der angeforderten Zeit.

Beispiele aus `legacy-v1` bei nominell 200 ms:

- 15° ungefähr 149 ms;
- 45° ungefähr 499 ms;
- 90° ungefähr 999 ms;
- 135° ungefähr 1399 ms;
- 180° ungefähr 1899 ms;
- ein gewrapptes 270°-Ziel ungefähr 999 ms auf dem kurzen Bogen.

Die Legacy-Kohorte erreichte 147/150 Endpunkte, aber nur 17/141 anwendbare
Dauerprüfungen. Drei bewegte 180°-Fälle liefen mit ungefähr 4° Restfehler in den
Timeout.

### 7.2 Vorher-Artefakt und Benchmark

Vor der Implementierung wurde der alte Controller unter
`build/rotation-benchmark/private/controller-before/` archiviert und gehasht.
Danach entstand eine neue deterministische Benchmark-Infrastruktur:

- `tests/rotation/reference.py` – 50 fest definierte Szenarien;
- `tests/rotation/metrics.py` – reine Trace-Auswertung;
- `tests/rotation/live.py` – Live-Harness;
- `tools/rotation_benchmark.py` – Fixture-/Run-Steuerung.

Die Szenarien decken 100/200/400 ms, Yaw, Pitch, kombinierte Achsen,
Wraparound, Bewegung, Cancellation, Supersession und Sequenzen ab.

### 7.3 Native Implementierung

Neu hinzu kam `src/main/java/dev/blockwire/RotationController.java`.

Der Controller:

- hält genau einen Plan pro Actor;
- verwendet `System.nanoTime()`;
- interpoliert auf echten Client-Ticks;
- unterstützt `linear` und `smoothstep`;
- verwendet den kürzesten äquivalenten Yaw-Bogen;
- klemmt Pitch auf den gültigen Bereich;
- bewegt Yaw und Pitch gleichzeitig;
- setzt am Ende exakt das äquivalente Ziel;
- startet ein neues Ziel von der **tatsächlich aktuell angewendeten** Sicht;
- startet identische aktive Ziele nicht erneut;
- besitzt keine Movement-Taste;
- meldet active/completed/cancelled/superseded und Sessionwechsel.

### 7.4 Protokoll- und SDK-Kompatibilität

Der bestehende `look`-Befehl erhielt optionale Felder:

- `duration_ms`: strikter Integer 1…5000;
- `rotation_profile`: `linear` oder `smoothstep`.

Wird `duration_ms` weggelassen, bleibt das alte unmittelbare `look`-Verhalten
unverändert. Ein Profil ohne Dauer wird vor jedem Effekt abgelehnt.

`Player.look(...)` erhielt dieselbe strikte Validierung. Oberhalb davon führt
`rotate_view_timed(...)` normale Nicht-Kampf-Drehungen standardmäßig als 200-ms-
Smoothstep aus und prüft Deadline sowie Actor-Bindung vor dem Request.

Die BCL-Signaturen blieben unverändert. V2 verwendet intern dieselbe generische
zeitbasierte Rotation und verifiziert weiterhin die beobachtete Orientierung.

### 7.5 Lifecycle und Lease-Trennung

Ursprünglich führte jedes Input-Release auch zu einem globalen Kameraabbruch. Das
war für unabhängige Movement- und Kamera-Leases falsch.

Deshalb wurde in `Blockwire.java` getrennt:

- `releaseInputs()` – gibt nur native Eingabetasten und deren Leases frei;
- `release()` – globaler Stop, der zusätzlich den Kameraplan abbricht.

Folge:

- natürliche Movement-Lease-Expiry stoppt keine unabhängige Rotation;
- F8, explizites Stoppen, Authority-Verlust, Actor-/Weltwechsel, Tod, Pause oder
  UI-Wechsel brechen den Plan weiterhin ab.

### 7.6 Telemetrie und Observation

`observe` enthält nun den Zustand des aktuellen oder letzten Kameraplans.
`MotionTrace` zeichnet pro Tick zusätzlich auf:

- Rotation-ID und Status;
- Ziel-Yaw/-Pitch;
- angeforderte Dauer;
- Profil.

Ein Scheduling-Receipt bleibt ausdrücklich **kein** Endpunktnachweis.

### 7.7 Migration der normalen Aufrufer

Die alte feste Turn-Implementierung wurde aus den normalen Nicht-Kampf-Pfaden
entfernt. Migriert wurden insbesondere:

- `approaching.py`;
- `excavating.py`;
- `eating.py`;
- `viewing.py`;
- `item_actions.py`;
- `woodcutting.py`;
- `searching.py`;
- die normale Navigation in `motion.py`.

Gestoppte visuelle Scans verwenden nun höchstens 17 Beobachtungen um vier native
90°-Ziele statt 46 einzelner 8°-Schritte.

Combat-Verhalten wurde absichtlich nicht migriert und bleibt separat.

### 7.8 Tests und Mutationen

Neue deterministic Contracts umfassen:

- RT01–RT06 in `python/tests/test_rotation.py`;
- RB01–RB05 in `python/tests/test_rotation_benchmark.py`;
- 39 native Checks in `RotationContractTest.java`;
- zusätzliche Continuous-Motion-Verträge;
- Mutationen für Dauer, Profil, shortest yaw, Deadline-Reihenfolge,
  Interpolation, Actor-Fence, exakten Endpunkt, Retargeting,
  Lease-Unabhängigkeit und Legacy-Kompatibilität.

Die simulierten Player wurden so erweitert, dass sie elapsed-time Interpolation,
Retargeting, Idempotenz und Cancellation abbilden. Diese Tests sind Contracts,
nicht alleinige Minecraft-Akzeptanz.

---

## 8. Benchmark- und Integrationskorrekturen während der Rotationseinführung

### 8.1 Analysefehler im Benchmark-Harness

Die ersten Post-change-Auswertungen deckten Fehler in der Messlogik auf:

- ein alter `cancelled`-Plan konnte fälschlich dem nächsten Lauf zugeordnet werden;
- No-op-Rotationen durften keine normale Dauerprüfung erhalten;
- Duration-Gates mussten nur auf anwendbare Fälle zählen.

Diese Fehler lagen in der Benchmark-Auswertung, nicht in einer nachträglichen
Umetikettierung der Runs. Die Rohdaten und fehlgeschlagenen Versuche blieben
erhalten. Danach entstanden die kanonischen Kohorten:

- `linear-v2`: 150/150, Dauer 141/141;
- `smoothstep-v2`: 150/150, Dauer 141/141;
- jeweils null Instant-Snaps und null verlorene Telemetriesamples.

Smoothstep blieb der 200-ms-Default, weil das Profil an Start und Ende eine
mathematisch geglättete Steigung besitzt. Linear bleibt explizit wählbar.

### 8.2 Movement-Regression: `combined_xyz`

Ein früher Post-rotation-Movement-Lauf zeigte Fehler in `combined_xyz`.
Ursachen waren:

1. temporär unvollständige Support-Beobachtungen;
2. W/A/S/D-Quantisierung gegen einen veralteten Yaw-Wert während einer laufenden
   zeitbasierten Drehung.

Korrekturen:

- bei transienter Support-Unsicherheit stoppen und neu planen;
- vor der Richtungsquantisierung eine frische actor-fenced Sicht verwenden;
- CM15 und CM16 als Regressionstests und passende Mutationen.

Danach bestand `after-rotation-v3` 211/211.

### 8.3 Bau-Regression A16: abgelaufenes separates Gateway-Zertifikat

A16 endete vor jeder Operation, weil das ausschließlich für den privaten
Benchmark verwendete Gateway-Zertifikat abgelaufen war.

Es wurde eine neue private Benchmark-Identität erzeugt. Dieser administrative
Fehler wurde nicht als Gameplay-Fehler oder Erfolg umetikettiert; A16 bleibt ein
Null-Operations-Fehllauf.

### 8.4 Bau-Regression A17: Drehung auf schmalem erhöhtem Support

A17 erreichte 48/71 erforderliche Blöcke und fiel dann während einer kombinierten
Dreh-/Fahrphase auf einem schmalen erhöhten Weg.

Die generische Korrektur `_broad_steering_support(...)` erlaubt Turn/Drive-
Überlappung nur, wenn frische seitliche Supportzellen sowohl am Quell- als auch am
Vorwärtsbereich nachgewiesen sind. Andernfalls wird gestoppt und neu geplant.

CM17 und eine gezielte Mutation decken diese Grenze ab. Eine 14/14-Safety-Smoke-
Kohorte bestand danach.

### 8.5 Bau-Regression A18: formal gültige, aber ungünstige Placement-Pose

A18 erreichte 46/71 erforderliche Blöcke. Ein Walk endete innerhalb des erlaubten
0,3-Block-Radius, aber seitlich so versetzt, dass keine exakte Supportfläche für
die nächste Platzierung getroffen werden konnte.

Die Korrektur in `item_actions.py`:

- akzeptiert eine bestehende Auto-position-Pose nur noch, wenn sie präzise genug
  am bekannten Zellzentrum liegt;
- wählt ansonsten den möglichst zentrierten bekannten sicheren Placement-Punkt;
- behält den 0,15-Block-Placement-Ankunftsradius und die vollständige
  Reach-/Body-Intervallprüfung bei.

Dazu kamen ein Placement-Contract und Mutationen für Recentering und
Center-Preference.

### 8.6 Frischer Bau-Erfolg A19

A19 startete wieder vom unveränderten geschlossenen Baseline-Snapshot und bestand:

- 71/71 erforderliche Blöcke;
- 288 ausgeführte Operationen;
- 82 verifizierte native Placement-Events;
- null fehlgeschlagene Aktionen;
- alle Eingang-, Innenraum-, Zugangs-, Dach-, Boden- und Safe-player-Prädikate;
- 342,66 Sekunden Laufzeit.

A16–A18 wurden nicht fortgesetzt und nicht in A19 umgewandelt.

### 8.7 Finale Movement- und Rotation-Runs

Gegen den finalen Produktionsquellstand lief anschließend:

- `after-rotation-v4`: 211/211 Movement-Repetitionen;
- 17.908 Gesamtticks, Median 70;
- 227 Full-stop-Runs;
- 1.756 Inputwechsel;
- maximaler Horizontalfehler `0.2900973203315447`;
- kein Gesundheitsverlust;
- alle Runs settled;
- null verlorene Trace-Samples.

Ein finaler Smoothstep-Source-Smoke bestand 8/8 mit 7/7 anwendbaren
Dauerprüfungen und null Instant-Snaps.

---

## 9. Finale Qualifikationsentscheidungen

| Bereich | Entscheidung | Grundlage |
|---|---|---|
| Native zeitbasierte Rotation | **GO** | Linear 150/150, Smoothstep 150/150, Dauer jeweils 141/141 |
| Movement nach Rotation | **GO** | unveränderte 211er-Kohorte: 211/211 |
| Frische deterministische Bau-Regression | **GO** | A19: 71/71 und alle unabhängigen Prädikate |
| Historischer Superflat Test A | **GO** | eingefrorene A11–A13-Kohorte 3/3 |
| Historischer Superflat Test B | **NO-GO** | B01 ohne finale Cleanup-/Zugangsakzeptanz |
| Strikte native Movement-Performance-Parität | **NO-GO** | historische Tick-Parität nicht erreicht |

Die drei positiven Gates ersetzen einander nicht. Ein Rotations-Erfolg kann keinen
Movement- oder Baufehler verdecken.

---

## 10. Finale QA

Auf dem qualifizierten Quellstand wurden ausgeführt:

- **455 Python-Tests: PASS**;
- Gradle `check`: **PASS**;
- native Rotation Contracts: 39 Checks;
- MotionTrace Contracts: 12 Checks;
- Controller-Lease-/Wiring-Contracts: 45 Checks;
- Terrain Contracts: 18 Checks;
- reale Netty/Python-TLS-Interoperabilität: **10/10 PASS**;
- Skill-Mutationen: 155/155 killed;
- native Mutationen: 46/46 killed;
- Controller-Mutationen: 20/20 killed;
- Building-Mutationen: 22/22 killed;
- insgesamt **243/243 killed**.

Der qualifizierte Test-JAR besitzt SHA-256:

```text
898c596dffa2ecf29f81f95a30df16d91a0d759f3ced9d3ed35efa7083eeee31
```

Der Client wurde abschließend am Title Screen ohne geladene Welt und ohne aktiven
Kameraplan beobachtet, über den nativen `Quit Game`-Button beendet, und die nur
noch wartenden eigenen Launcher-Wrapper wurden danach beendet. Port 8765 war
geschlossen.

Der abschließende `ccc index` erfasste 281 Dateien und 3597 Chunks ohne Fehler.

---

## 11. Wichtige geänderte Dateien

### Native Java-Schicht

| Datei | Änderung |
|---|---|
| `src/main/java/dev/blockwire/RotationController.java` | neuer actor-bound elapsed-time Controller |
| `src/main/java/dev/blockwire/Blockwire.java` | Integration, Tick-Aufruf, `releaseInputs()`/globales `release()` |
| `src/main/java/dev/blockwire/Protocol.java` | Validierung von Dauer und Profil |
| `src/main/java/dev/blockwire/MotionTrace.java` | Rotation-Metadaten pro Client-Tick |
| `src/main/java/dev/blockwire/Observations.java` | Rotation-State in `observe` |
| `src/main/java/dev/blockwire/NavigationView.java` | konservative typed Movement-Geometrie |

### Python-Laufzeit und Skills

| Datei | Änderung |
|---|---|
| `python/src/blockwire/client.py` | striktes timed `Player.look(...)` |
| `python/src/blockwire/skills/motion.py` | timed rotation, frische Sicht, Support-gesteuerte Überlappung |
| `python/src/blockwire/skills/walking.py` | geometrische Routen und stabile Ankunft |
| `python/src/blockwire/skills/item_actions.py` | präzises Placement-Recentering |
| `python/src/blockwire/skills/approaching.py` | native zeitbasierte Nicht-Kampf-Drehung |
| `python/src/blockwire/skills/viewing.py` | beobachtete Endorientierung |
| `python/src/blockwire/skills/searching.py` | vier native Quarter-turn-Scans |
| `python/src/blockwire/skills/woodcutting.py` | timed Scan/Aim |
| `python/src/blockwire/skills/excavating.py` | actor-fenced timed Aim |
| `python/src/blockwire/skills/eating.py` | timed Nicht-Kampf-Sichtsteuerung |

### Benchmarks und Tests

| Datei/Verzeichnis | Zweck |
|---|---|
| `tests/rotation/` | Referenz, Live-Harness und reine Metriken |
| `tools/rotation_benchmark.py` | Rotation-Fixture und Live-Kohorten |
| `tools/report_rotation_benchmark.py` | finale getrennte Gates und Evidence-Erzeugung |
| `python/tests/test_rotation.py` | Python-Rotationsverträge |
| `python/tests/test_rotation_benchmark.py` | Benchmark-/Metrikverträge |
| `python/tests/test_continuous_motion.py` | Turn/Drive-, Fresh-view- und Support-Regressionen |
| `python/tests/test_placement.py` | Placement-Recentering und Pose-Wahl |
| `src/contractTest/java/dev/blockwire/RotationContractTest.java` | native Lifecycle-/Interpolation-Verträge |
| `tests/run_skill_mutations.py` | Python-Motor-/Rotation-/Placement-Mutationen |
| `tests/run_mutations.py` | native Rotations- und Lease-Mutationen |

---

## 12. Erhaltene Fehler und nicht geschlossene Bereiche

Bewusst nicht als Erfolg umetikettiert wurden unter anderem:

- die drei Legacy-Rotations-Timeouts;
- alle Movement-Zwischenkohorten vor 211/211;
- A16, A17 und A18;
- B01 trotz 71/71 physisch vorhandener Pflichtblöcke;
- Debug-Fortsetzungen und Recovery-Probes;
- die historische native Performance-Parität.

Weiterhin nicht allgemein qualifiziert sind:

- Slabs, Fluids und beliebige Collision-Shapes;
- allgemeine Höhlen und unbekannte Langstrecken;
- hostile, food-constrained oder unbeaufsichtigte Survival-Zuverlässigkeit;
- Nether-/End-Komplettprogression;
- breite Modpack-Kompatibilität;
- allgemeine Kampfkameramigration;
- 24/7-Betrieb oder Multi-Tenant-Steuerung.

Schadensvermeidung bleibt best effort und ist keine Immunität.

---

## 13. Evidence- und Artefaktkarte

Öffentliche, reviewbare Dokumente:

- `docs/rotation-benchmark.md`
- `docs/evidence/rotation-benchmark.json`
- `docs/movement-benchmark.md`
- `docs/evidence/movement-benchmark.json`
- `docs/superflat-building.md`
- `docs/evidence/superflat-building.json`

Wichtige lokale, ignorierte Artefakte:

- `build/rotation-benchmark/legacy-v1/`
- `build/rotation-benchmark/linear-v2/`
- `build/rotation-benchmark/smoothstep-v2/`
- `build/rotation-benchmark/smoothstep-final-smoke-v3/`
- `build/movement-benchmark/after-rotation-v4/`
- `build/superflat-benchmark/A16/` bis `A19/`
- `build/rotation-benchmark/final-verification/`

SHA-256 der finalen öffentlichen Rotation-Evidenz zum Zeitpunkt dieser
Dokumentation:

```text
e3dff08e98f8a8aa97fe0520939b7afb4a13b77d8dad9fc17ba953b2b8b1247c
```

Die lokalen Rohartefakte bleiben absichtlich außerhalb distributabler Bundles.

---

## 14. Veröffentlichungsstatus

Die beschriebenen Änderungen wurden lokal implementiert und qualifiziert. Der
Operator hat anschließend ausdrücklich einen lokalen Commit dieses Stands
autorisiert.

Nicht autorisiert und nicht erfolgt sind weiterhin:

- Push;
- Tag;
- Upload;
- Release;
- Produktionsdeployment.

Jede Veröffentlichung oder Installation außerhalb der ausdrücklich autorisierten
Testinstanz benötigt eine separate Freigabe.
