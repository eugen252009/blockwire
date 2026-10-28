# Configuration and menu startup

File, relative to the **Minecraft game directory**:
`config/blockwire/settings.json`.

Upgrades reuse an existing `config/block-bridge/` directory in place; no credentials
or certificates are regenerated for the rename. If both old/new directories exist,
startup fails closed. See [rename/upgrade](rename.md).

The first launch creates it with safe defaults and a random private API key.
Edit that generated file, retaining or replacing its key:

```json
{
  "enabled": true,
  "server_ip": "127.0.0.1",
  "port": 8765,
  "mcp_api_key": "<your generated private API key>"
}
```

The angle-bracket value is documentation only, **not a valid key**.
Keep the generated value or use a fresh random URL-safe key of 32–256 characters.
Allowed key characters: ASCII letters, digits, hyphen and underscore. No example
working key is shipped. Never commit or paste your real config/key into reports.

- **enabled:** true starts the endpoint at client startup, including the main
  menu, without a world or physical F8 press. Default false.
- **server_ip:** literal IPv4 or IPv6 bind address; no DNS lookup/hostname.
  Default `127.0.0.1`. `::1` is IPv6 loopback. A LAN IP or `0.0.0.0` / `::`
  is explicitly allowed but broadens network exposure.
- **port:** integer 1024–65535. Default 8765.
- **mcp_api_key:** authoritative bearer credential for the WebSocket/MCP adapter.
  Generated randomly on first launch. It is **not** an LLM provider API key.

F8 remains the local runtime kill switch even when auto-start is enabled. F8
does not rewrite the file: `enabled: true` will start again on the next launch.
Configuration is read at startup; restart after editing it. Invalid configuration
disables the bridge instead of falling back to a public listener.

Existing initial-version `{"port":8765}` configs migrate by adding disabled
startup, loopback bind and the existing private token. Unknown fields and wrong
types are rejected. The legacy private `token` file is refreshed from the key
for old Python scripts; edit `mcp_api_key`, not that mirror.

## Optional Mod Menu screen

Install a Minecraft-compatible **Mod Menu** alongside Blockwire and Fabric API.
The API integration is built/tested against **Mod Menu 21.0.0 for Minecraft 26.3**;
newer Mod Menu releases may target a different Minecraft version. Mod Menu is
optional and is neither bundled nor downloaded by Blockwire.

Open **Mods → Blockwire → Configure** from the title or pause menus. English and
German translations are included. The screen shows endpoint enabled/disabled,
controller connected/waiting, the configured TLS address and the local stop hint.
It exposes no API key, token, certificate/private-key data or text-field secret.

- **Enable control now / Disable control and release inputs** uses the same
  runtime lifecycle as F8. Changes are immediate, including releasing owned input
  on stop; bind failure is not reported as enabled. It does not change startup
  preferences, connect Python, or activate autopilot.
- **Enable at next launch** changes a draft. **Save startup preference** explicitly
  writes only `enabled` to the already-selected settings file. It does not start,
  stop or rebind the current endpoint. Closing with Done/Escape discards unsaved
  drafts; already-applied runtime toggles are not rolled back. Resizing retains
  the draft. F8 remains usable and the screen refreshes runtime status.
- IP/port/key edits and credential rotation remain manual, with Minecraft stopped
  and a restart afterward. No key reveal/copy/reset or trust-bypass control exists.
- If private configuration/TLS initialization failed, runtime/save controls stay
  disabled. Fix the local configuration and restart; opening this screen does not
  silently repair, regenerate or replace an identity.

Saving preserves the existing new/legacy config directory, API key, bind/port,
compatibility token and TLS identity. It validates the complete existing config,
rejects missing/symlink/stale authority, writes a private temporary file, and
requires an atomic replacement. Filesystems without atomic replacement report
failure instead of falling back to a partial write. Stale-file checks are best
effort under the trusted-local-filesystem assumption, not a filesystem transaction
against arbitrary concurrent external writers. Stop Minecraft before externally
changing address/keys. A save failure is shown without logging credentials.

As with other native menus, an already authorized MCP controller can navigate
this screen through native menu events. There is no new settings/file RPC.
Opening it does not start an AI: goals and autopilot still run explicitly in the
external Python/MCP host. The screen does not edit those running job policies.

Component contracts cover optional API linkage, no effects on opening, draft/save
separation, failure paths, private persistence, stale/symlink rejection and unchanged
token/TLS bytes. **Graphical Mod Menu screen acceptance: NOT RUN.** Source/API
compilation and headless contracts are not evidence of live layout/input behavior.
Current artifact/source/log hashes: [Mod Menu evidence](evidence/modmenu.json).
Development checks passed: 32 settings + 4 optional-API assertions, Gradle build/check,
44 Python tests, 10 packaging tests, real TLS interoperability, and 19 Java + 11
Python skill mutations (five Java mutations exercise the new settings contracts).

## Python / MCP host

Prefer:
```sh
export BLOCKWIRE_CONFIG="/absolute/path/to/minecraft/config/blockwire/settings.json"
blockwire menu
blockwire-mcp
```

`BLOCKWIRE_URL` optionally overrides the client's destination (not the mod's
bind). For a wildcard bind, the local adapter defaults to loopback. Remote adapters
must use the actual reachable host IP and matching API key, not `0.0.0.0`.
The mod terminates TLS itself; use **`wss://` only**. Local adapters automatically
trust the instance's `tls/certificate.pem`. For a remote instance, securely copy
that public certificate and set `BLOCKWIRE_CERT_FILE` to its trusted local path.
Do not copy `tls/identity.p12`. See [TLS details](tls.md).

MCP here is **stdio** between your agent host and the Python adapter. The network
listener in Minecraft is WebSocket; this is not an unauthenticated HTTP MCP server.

## Privacy and exposure

The directories are 0700 and config/token/TLS files 0600 on POSIX. On Windows use private
user ACLs. The Python adapter refuses group/world-readable key files on POSIX.
TLS 1.2/1.3 is always required, including loopback. Each instance creates its own
certificate on first startup and reuses it thereafter. Initial certificate trust
must be established locally or out of band; there is no trust-all fallback.
Keep firewall/trusted-client restrictions. TLS/API authentication is not DoS protection.

Rotate a key by stopping Minecraft, replacing `mcp_api_key` with a fresh random
key in the private config, and restarting. Update remote adapters accordingly.
