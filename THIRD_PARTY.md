# Bundled libraries

The mod includes these libraries as Fabric nested dependencies (Loom adds Fabric
packaging metadata; library classes are not shaded or rewritten):

- Bouncy Castle `bcprov-jdk18on` **1.84**
- Bouncy Castle `bcutil-jdk18on` **1.84**
- Bouncy Castle `bcpkix-jdk18on` **1.84**

Purpose: standard X.509 certificate construction/signing. TLS itself uses JDK JSSE.
Their upstream license text is reproduced in [licenses/BouncyCastle.txt](licenses/BouncyCastle.txt)
and bundled in the mod under `META-INF/licenses/`. Upstream: https://www.bouncycastle.org/ ; license:
https://www.bouncycastle.org/licence.html . They increase the mod JAR to about 9 MB.

Minecraft, Fabric and Netty are provided by the game/loader/API installation and
are not repackaged as part of this project's code. Blockwire's own code is MIT.
