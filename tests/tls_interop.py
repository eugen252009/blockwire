#!/usr/bin/env python3
"""Real Netty TLS -> Python SSL/WebSocket contracts, isolated from Minecraft worlds."""
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import time
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus
from blockwire import Bridge

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("BLOCKWIRE_VERIFICATION_DIR", ROOT / "build/tls-verification"))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    checks = []
    with tempfile.TemporaryDirectory(prefix="blockwire-tls-interop-") as directory:
        folder = Path(directory)
        (folder / "running").touch()
        with (OUT / "fixture.log").open("w") as log:
            process = subprocess.Popen(["./gradlew", "--console=plain", "tlsFixture", f"-PfixtureDir={folder}"],
                                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            try:
                for _ in range(1200):
                    if (folder / "ready.json").exists():
                        break
                    if process.poll() is not None:
                        raise AssertionError("TLS fixture exited; inspect fixture.log")
                    time.sleep(.05)
                config = json.loads((folder / "ready.json").read_text())
                url, certificate = config["url"], config["certificate"]
                bridge = Bridge("a"*64, url, certificate=certificate)
                context = bridge.tls_context()
                assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED, "certificate_and_hostname_verification_enabled"
                assert len(context.get_ca_certs(binary_form=True)) == 0  # Trusted leaf is not a CA.
                checks.append("certificate_and_hostname_verification_enabled")
                with bridge:
                    assert bridge._socket.socket.version() in ("TLSv1.2", "TLSv1.3")
                    assert bridge.call("observe")["calls"] == 1
                time.sleep(.1)
                checks.append("encrypted_authorized_exchange")
                for label, cert, hostname in [
                    ("wrong_instance_certificate", config["wrong_certificate"], Bridge.TLS_NAME),
                    ("wrong_service_hostname", certificate, "wrong-instance.invalid"),
                ]:
                    context = Bridge("a"*64, url, certificate=cert).tls_context()
                    try:
                        with connect(url, ssl=context, server_hostname=hostname, proxy=None,
                                     additional_headers={"Authorization": "Bearer "+"a"*64}, open_timeout=3):
                            raise AssertionError(label)
                    except ssl.SSLCertVerificationError:
                        checks.append(label)
                try:
                    with connect(url, proxy=None, open_timeout=3):
                        raise AssertionError("system_roots_must_not_trust_instance")
                except ssl.SSLCertVerificationError:
                    checks.append("unknown_certificate_rejected_by_default")
                try:
                    with Bridge("b"*64, url, certificate=certificate):
                        raise AssertionError("wrong_key")
                except InvalidStatus as error:
                    assert error.response.status_code == 403
                    checks.append("api_key_still_required")
                port = int(url.split(":")[2].split("/")[0])
                with socket.create_connection(("127.0.0.1", port), timeout=3) as raw:
                    raw.sendall(b"GET /v1 HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\n\r\n")
                    try:
                        response = raw.recv(8192)
                    except ConnectionResetError:
                        response = b""
                    assert b"101 Switching" not in response and b"HTTP/" not in response
                    checks.append("plaintext_http_rejected")
                # All failed trust/HTTP/auth attempts must precede protected dispatch.
                with Bridge("a"*64, url, certificate=certificate) as verified:
                    assert verified.call("observe")["calls"] == 2
                checks.append("invalid_peers_never_dispatched")
                # Verify both protocol versions with the same trusted leaf/name.
                for protocol in [ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3]:
                    time.sleep(.1)
                    context = bridge.tls_context()
                    context.minimum_version = context.maximum_version = protocol
                    with connect(url, ssl=context, server_hostname=Bridge.TLS_NAME, proxy=None,
                                 additional_headers={"Authorization": "Bearer "+"a"*64}) as connection:
                        assert connection.socket.version() in ("TLSv1.2", "TLSv1.3")
                    checks.append(protocol.name)
            finally:
                (folder / "running").unlink(missing_ok=True)
                try:
                    code = process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=5)
                    raise AssertionError("fixture did not stop normally")
                assert code == 0, code
    (OUT / "interop.json").write_text(json.dumps({"status": "PASS", "checks": checks}, indent=2)+"\n")
    print("TLS_INTEROP_PASS checks="+str(len(checks)))


if __name__ == "__main__":
    main()
