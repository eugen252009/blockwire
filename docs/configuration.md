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
