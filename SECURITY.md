# Security model

Blockwire gives an authorized program control of a Minecraft player and access
to client-known inventory/world information. Protect the API key and TLS identity.

## Transport and identity

- Disabled by default. Explicit local config `enabled: true` authorizes startup
  from the main menu; F8 remains the local runtime kill switch.
- Explicit literal IPv4/IPv6 bind; loopback default. Non-loopback binding still
  requires trusted clients and a firewall.
- **Mandatory TLS 1.2/1.3 before HTTP/WebSocket processing. No plaintext listener,
  protocol sniffing/downgrade, or insecure-client option.**
- Each instance generates an independent P-256 EC private key and self-signed
  SHA-256/ECDSA server certificate at first startup, even while control is disabled.
  It persists, expires after ten years and never silently renews/replaces a damaged
  or incomplete existing identity.
- Certificate generation uses bundled Bouncy Castle tooling; TLS uses the JDK's
  provider through Netty. No shell/keytool invocation or JDK-internal API.
- Python uses a dedicated trust store containing only the explicitly selected
  instance certificate. Certificate and hostname verification stay enabled.
  The logical TLS name is `block-bridge.invalid`, independent of the connection IP.
  It is intentionally retained across the Blockwire rename to preserve existing trust.
  Initial remote certificate distribution must use an already trusted channel.
- TLS authenticates the server, not the controller. WebSocket upgrade separately
  requires `Authorization: Bearer <key>`; URL credentials and Origin headers are
  rejected. The API key is sent only after the verified TLS handshake.
- Generated directory permissions: 0700; config, compatibility token, TLS
  identity and certificate files: 0600 on POSIX. On non-POSIX systems protect
  the game directory with user-only ACLs.
- The private PKCS12 identity has an empty store password: filesystem access is
  the security boundary, not a password stored beside the key. Its exported
  certificate contains no private key and may be copied to trusted clients.
- Atomic identity persistence, serialized generation, missing-export recovery
  from the same identity; malformed/mismatched/expired identities fail closed.

## Authority and lifecycle

- One controller, at most eight peers, 8 KiB request/frame limit, 32 queued game
  tasks, two-second queued-request expiry, five-second TLS handshake timeout and
  30-second network read timeout.
- All game access runs on the client thread. Disconnected controllers cannot run
  queued actions. Ownership cleanup precedes reuse; generation checks prevent
  an old endpoint releasing a new endpoint's held input.
- Holds expire by ticks and monotonic deadline. Cleanup requires the game thread
  to advance; no real-time release guarantee during a JVM/OS stall.
- Inputs release on unexpected dispatch errors. No command RPC, arbitrary code,
  file API, NBT evaluation, remote container opening or creative cloning.
- Native menu control can create/delete worlds, join servers, change options and
  open native external links. Do not authorize destructive actions casually.
  Chat screens are not controllable. Text values are redacted, but other menu
  labels can contain personal world/server names.
- World/server/item labels are untrusted data, never authorization/instructions.
  No telemetry or model connections are added; Minecraft's usual services remain.

## Descriptive skills and trusted extensions

High-level planning runs in the Python host, not as remote code in Minecraft.
Only explicitly selected installed `blockwire.skills` entry points load;
there is no RPC to install/import arbitrary modules. Providers execute ordinary
trusted Python and are **not sandboxed**. Review LLM-generated extensions before
installing/enabling them.

One background job owns the actor. Raw mutating MCP tools reject concurrent
control; observations, status and cancel remain available. Deadlines/cancellation
are cooperative, with native short holds and F8 as separate safeguards. Walking
uses an actor-session fence on every look/drive and always attempts final release.

The navigation observation exposes at most 81 loaded same-level collision cells,
not arbitrary world/block/NBT queries or new chunk generation. Known hazard/mob
checks are incomplete. `avoid_damage` is never a no-damage/no-death guarantee.

## Boundaries and rotation

TLS does not sandbox malicious processes running as your OS user, administrators,
modified mods, compromised agent hosts or compromised Minecraft. Those actors may
read keys or act inside the process. TLS is not comprehensive Internet DoS
protection; do not treat this alpha as a hardened public service.

Rotate the API key by stopping Minecraft and replacing `mcp_api_key` in the private
config. Deleting the compatibility token alone does not rotate it.

Certificate rotation is a separate, explicit operation: stop Minecraft, archive
the old identity privately if needed, remove its TLS directory, relaunch, and
re-enroll the new public certificate on every client through a trusted channel.
Never automatically accept a replacement fetched from the endpoint. See
[docs/tls.md](docs/tls.md). Do not include private identities, credentials, game
directories or account data in reports.

A real private vulnerability-reporting contact must be selected before publication;
no hosted project/contact URL has been invented.
