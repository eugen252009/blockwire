# TLS and per-instance trust

TLS behavior remains current in 0.2. The counts/manifest below record the preserved
0.1 TLS qualification; current skill/packaging evidence is [skills.md](skills.md).

**Current transport: encrypted WebSockets only, `wss://`, with TLS 1.2/1.3.**
Update the Minecraft mod and Python package together; old `ws://` clients are
intentionally rejected rather than silently downgraded.

## First startup

The mod generates, inside the instance's Minecraft game directory:

- `config/blockwire/tls/identity.p12` — **private key + certificate; never share**.
- `config/blockwire/tls/certificate.pem` — public certificate for trusted clients.

No extra config switch or external executable is needed. Generation happens even
if bridge control is disabled. Auto-start from the main menu, configured IP/port,
API-key authentication and F8 emergency stop continue to work.

Each instance gets a different P-256 EC key and SHA-256/ECDSA self-signed leaf
certificate. Bouncy Castle handles X.509 construction; JDK JSSE through Netty
handles TLS. The certificate is valid for ten years, reused on restarts and is
**not a certificate authority**. The private store is protected by file permissions,
not a secret password stored alongside it (its store password is empty).

## Local Python / MCP connection

Keep the existing environment setting:
```sh
export BLOCKWIRE_CONFIG="/path/to/minecraft/config/blockwire/settings.json"
blockwire menu
blockwire-mcp
```

The adapter automatically selects `wss://` and the public certificate next to the
config. The legacy token-file factory also discovers that certificate. A direct
Python constructor must supply its trusted certificate:

```python
with Bridge(api_key, "wss://127.0.0.1:8765/v1",
            certificate="/trusted/path/certificate.pem") as bridge:
    print(bridge.call("menu"))
```

## Remote connection / initial enrollment

1. Obtain the instance's **public** `certificate.pem` through an already trusted
   channel (local access, authenticated SSH/file transfer, etc.).
2. Verify its SHA-256 fingerprint against the operator's independently obtained
   value if needed:
   `openssl x509 -in certificate.pem -noout -fingerprint -sha256`.
3. Configure the adapter with the API key, reachable network address and trusted
   certificate path:
```sh
export BLOCKWIRE_CONFIG="/private/client/settings.json"
export BLOCKWIRE_URL="wss://192.168.1.20:8765/v1"
export BLOCKWIRE_CERT_FILE="/trusted/instance-certificate.pem"
```

Do not fetch an unknown certificate over the same untrusted connection and
automatically accept it. Never distribute `identity.p12`. Keep private API-key
config files user-only (0600 on POSIX).

### Why a logical TLS name?

The legacy spelling in that service identifier is intentional: Blockwire retains
it so a product rename does not rotate private keys or invalidate trusted
certificates. See [rename compatibility](rename.md).

The SDK checks the name **`block-bridge.invalid`**, a reserved logical service
identity, while connecting to the configured IP/URL. This keeps certificate and
hostname verification **enabled** without regenerating trust when a LAN IP changes.
It does not perform DNS resolution for that logical name.

Peer identity comes from trusting the specific instance's certificate, not from a
shared public CA or merely recognizing that name. A different instance's certificate
is rejected even though its service name is the same. The dedicated Python SSL
context has no system CA roots and no trust-all switch. Loopback SANs are also
included for standard local TLS clients. Other custom clients should send/check
the logical TLS server name and trust only the selected instance certificate.

TLS verification completes **before** the HTTP upgrade sends the API key.
Server identity and API-key controller authorization remain independent.

## Failure and rotation

Corrupt, mismatched, expired or missing-private-key identities fail closed: no
listener/plaintext fallback and no automatic trust replacement. A missing public
export is recreated only from the same existing private identity.

To deliberately rotate: stop Minecraft, privately archive/remove the instance's
TLS directory, restart, and re-enroll the newly generated public certificate on
all clients through a trusted channel. Remove archived private keys when no longer
needed. Do not rotate automatically on each launch or “fix” errors with
`CERT_NONE`, disabled hostname checking or a downloaded replacement certificate.

First-write persistence is atomic, generation is serialized, and interrupted
temporary files are not promoted. This is not a guarantee against arbitrary
filesystem corruption, malicious same-user processes or operating-system failure.

## Executed qualification

| Check | Status |
|---|---|
| Existing Java transport/input/config contracts, now over TLS | PASS: 54 |
| TLS identity lifecycle, uniqueness, persistence, permissions, expiry, corruption, missing-key/export, symlink checks | PASS: 19 |
| Python SDK contracts | PASS: 13 |
| Real Netty ↔ Python TLS/WebSocket exchanges, TLS 1.2 and 1.3 | PASS: 10 |
| Wrong certificate, wrong TLS name, untrusted certificate, plaintext and invalid API key rejected before protected dispatch | PASS |
| Seven isolated Java mutations + one Python verification-bypass mutation | KILLED: 8 |
| Packaged JAR + Fabric API, fresh genuine graphical Minecraft instance; first-start certificate generation; native menu navigation through MCP/TLS | PASS |
| Same packaged instance restarted; identical certificate and verified connection | PASS |
| External LAN routing, Windows/macOS, full gameplay/two-client regression | NOT RUN |

The packaged smoke used an isolated official client/Fabric profile and no Echoes
mod, account database or world. Its retained launch attempt first encountered the
helper's stopped loopback quick-play target; MCP returned through native menus and
successfully navigated Title → Options → Title over verified TLS. This is not a
multiplayer/gameplay acceptance result.

Current hashes/results: [evidence/tls.json](evidence/tls.json). Raw local evidence:
`build/tls-verification/`. The prior artifact/source/docs and raw verification
were preserved under `build/qualification/pre-tls/`; the previous
[evidence manifest](evidence/verification.json) remains historical.

Reproduce:
```sh
./gradlew build
.venv/bin/python -B -m unittest discover -s python/tests -v
.venv/bin/python -B tests/tls_interop.py
BLOCKWIRE_VERIFICATION_DIR="$PWD/build/tls-verification" python3 tests/run_mutations.py
.venv/bin/python tests/run_tls_client_mutation.py
./gradlew check --rerun-tasks
```

TLS is not Internet DoS hardening, a sandbox or release approval. Do not publish
private keys, API credentials, game directories or bundled account information.
