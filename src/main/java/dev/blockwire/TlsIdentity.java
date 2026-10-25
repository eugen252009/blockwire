package dev.blockwire;

import io.netty.handler.ssl.*;
import java.io.*;
import java.math.BigInteger;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.*;
import java.security.cert.*;
import java.security.spec.ECGenParameterSpec;
import java.time.*;
import java.util.*;
import org.bouncycastle.asn1.x500.X500Name;
import org.bouncycastle.asn1.x509.*;
import org.bouncycastle.cert.jcajce.*;
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder;

/** Persistent self-signed leaf identity, generated once. No global JCA provider changes. */
public record TlsIdentity(SslContext context,X509Certificate certificate,Path certificateFile) {
    // Stable wire identity, deliberately retained so renaming never invalidates existing certificates.
    public static final String TLS_NAME="block-bridge.invalid";
    private static final char[] STORE_PASSWORD=new char[0]; // Filesystem permissions protect the key.
    public static TlsIdentity load(Path configDir) throws IOException {
        Path dir=configDir.resolve("tls");
        if(Files.isSymbolicLink(configDir) || Files.isSymbolicLink(dir))throw new IOException("symlink_tls_directory");
        Files.createDirectories(dir);permissions(dir,"rwx------");
        Path store=dir.resolve("identity.p12"),pem=dir.resolve("certificate.pem"),lock=dir.resolve(".lock");
        for(Path path:List.of(store,pem,lock))if(Files.isSymbolicLink(path))throw new IOException("symlink_tls_file");
        if(!Files.exists(lock)) {
            try {privateFile(lock);}catch(FileAlreadyExistsException ignored){}
        }
        permissions(lock,"rw-------");
        try(var channel=FileChannel.open(lock,StandardOpenOption.WRITE,LinkOption.NOFOLLOW_LINKS);
            var held=channel.tryLock()) {
            if(held==null)throw new IOException("tls_identity_busy");
            if(!Files.exists(store)) {
                if(Files.exists(pem))throw new IOException("tls_private_identity_missing_do_not_silently_rotate");
                generate(store);
            }
            permissions(store,"rw-------");
            KeyStore keys=KeyStore.getInstance("PKCS12");
            try(var input=Files.newInputStream(store)){keys.load(input,STORE_PASSWORD);}
            var cert=(X509Certificate)keys.getCertificate("instance");
            var key=(PrivateKey)keys.getKey("instance",STORE_PASSWORD);
            if(cert==null || key==null)throw new GeneralSecurityException("missing_tls_key_or_certificate");
            cert.checkValidity();cert.verify(cert.getPublicKey());
            if(cert.getBasicConstraints()!=-1 || cert.getExtendedKeyUsage()==null ||
                !cert.getExtendedKeyUsage().contains(KeyPurposeId.id_kp_serverAuth.getId()))
                throw new GeneralSecurityException("not_a_server_leaf_certificate");
            byte[] challenge=new byte[32];new SecureRandom().nextBytes(challenge);
            var proof=Signature.getInstance("SHA256withECDSA");
            proof.initSign(key);proof.update(challenge);byte[] signature=proof.sign();
            proof.initVerify(cert.getPublicKey());proof.update(challenge);
            if(!proof.verify(signature))throw new GeneralSecurityException("tls_key_mismatch");
            if(Files.exists(pem)) {
                try(var input=Files.newInputStream(pem)) {
                    var exported=CertificateFactory.getInstance("X.509").generateCertificate(input);
                    if(!MessageDigest.isEqual(exported.getEncoded(),cert.getEncoded()))
                        throw new IOException("tls_export_mismatch_do_not_silently_rotate");
                }
                permissions(pem,"rw-------");
            } else writeAtomic(pem,("-----BEGIN CERTIFICATE-----\n"+
                Base64.getMimeEncoder(64,new byte[]{'\n'}).encodeToString(cert.getEncoded())+
                "\n-----END CERTIFICATE-----\n").getBytes(java.nio.charset.StandardCharsets.US_ASCII));
            SslContext context=SslContextBuilder.forServer(key,cert).sslProvider(SslProvider.JDK)
                .protocols("TLSv1.3","TLSv1.2").build();
            return new TlsIdentity(context,cert,pem);
        } catch(GeneralSecurityException | java.nio.channels.OverlappingFileLockException e) {
            throw new IOException("invalid_or_busy_tls_identity",e);
        }
    }
    private static void generate(Path store) throws IOException,GeneralSecurityException {
        var random=new SecureRandom();
        var generator=KeyPairGenerator.getInstance("EC");
        generator.initialize(new ECGenParameterSpec("secp256r1"),random);
        var pair=generator.generateKeyPair();
        var name=new X500Name("CN="+TLS_NAME);
        Instant now=Instant.now();
        var builder=new JcaX509v3CertificateBuilder(name,new BigInteger(159,random).add(BigInteger.ONE),
            Date.from(now.minusSeconds(300)),Date.from(now.plus(Duration.ofDays(3650))),name,pair.getPublic());
        try {
            builder.addExtension(org.bouncycastle.asn1.x509.Extension.basicConstraints,true,new BasicConstraints(false));
            builder.addExtension(org.bouncycastle.asn1.x509.Extension.keyUsage,true,new KeyUsage(KeyUsage.digitalSignature));
            builder.addExtension(org.bouncycastle.asn1.x509.Extension.extendedKeyUsage,false,new ExtendedKeyUsage(KeyPurposeId.id_kp_serverAuth));
            builder.addExtension(org.bouncycastle.asn1.x509.Extension.subjectAlternativeName,false,
                new GeneralNames(new GeneralName[]{new GeneralName(GeneralName.dNSName,TLS_NAME),
                    new GeneralName(GeneralName.dNSName,"localhost"),new GeneralName(GeneralName.iPAddress,"127.0.0.1"),
                    new GeneralName(GeneralName.iPAddress,"::1")}));
            var extensions=new JcaX509ExtensionUtils();
            builder.addExtension(org.bouncycastle.asn1.x509.Extension.subjectKeyIdentifier,false,
                extensions.createSubjectKeyIdentifier(pair.getPublic()));
            builder.addExtension(org.bouncycastle.asn1.x509.Extension.authorityKeyIdentifier,false,
                extensions.createAuthorityKeyIdentifier(pair.getPublic()));
            var signer=new JcaContentSignerBuilder("SHA256withECDSA")
                .setProvider(new org.bouncycastle.jce.provider.BouncyCastleProvider()).build(pair.getPrivate());
            var cert=new JcaX509CertificateConverter().getCertificate(builder.build(signer));
            cert.verify(pair.getPublic());
            var keys=KeyStore.getInstance("PKCS12");keys.load(null,STORE_PASSWORD);
            keys.setKeyEntry("instance",pair.getPrivate(),STORE_PASSWORD,new java.security.cert.Certificate[]{cert});
            var bytes=new ByteArrayOutputStream();keys.store(bytes,STORE_PASSWORD);
            writeAtomic(store,bytes.toByteArray());
        } catch(org.bouncycastle.operator.OperatorCreationException | org.bouncycastle.cert.CertIOException e) {
            throw new GeneralSecurityException("certificate_generation_failed",e);
        }
    }
    private static void privateFile(Path path) throws IOException {
        try {Files.createFile(path,PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));}
        catch(UnsupportedOperationException e){Files.createFile(path);}
    }
    private static void permissions(Path path,String value) throws IOException {
        try {Files.setPosixFilePermissions(path,PosixFilePermissions.fromString(value));}
        catch(UnsupportedOperationException ignored) {}
    }
    private static void writeAtomic(Path target,byte[] bytes) throws IOException {
        Path temporary=target.resolveSibling("."+target.getFileName()+"-"+UUID.randomUUID()+".tmp");
        try {
            privateFile(temporary);
            try(var channel=FileChannel.open(temporary,StandardOpenOption.WRITE)) {
                var buffer=java.nio.ByteBuffer.wrap(bytes);
                while(buffer.hasRemaining())channel.write(buffer);
                channel.force(true);
            }
            // No non-atomic fallback: unsupported filesystems fail closed.
            Files.move(temporary,target,StandardCopyOption.ATOMIC_MOVE);
        } finally {Files.deleteIfExists(temporary);}
    }
}
