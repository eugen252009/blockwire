package dev.blockwire;

import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.*;
import java.security.cert.*;
import java.util.*;
import javax.net.ssl.*;

public final class TlsContractTest {
    private static int checks;
    private static void check(boolean value,String label){if(!value)throw new AssertionError(label);checks++;}
    private interface Attempt {void run() throws Exception;}
    private static void refused(Attempt attempt,String label) throws Exception {
        try {attempt.run();throw new AssertionError(label);}
        catch(java.io.IOException expected){checks++;}
    }
    static SSLContext trust(X509Certificate certificate) throws Exception {
        var store=KeyStore.getInstance("PKCS12");store.load(null,null);store.setCertificateEntry("instance",certificate);
        var manager=TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());manager.init(store);
        var context=SSLContext.getInstance("TLS");context.init(null,manager.getTrustManagers(),null);return context;
    }
    static void deleteTree(Path path) throws Exception {
        try(var files=Files.walk(path)){for(var file:files.sorted(Comparator.reverseOrder()).toList())Files.delete(file);}
    }
    public static void main(String[] args) throws Exception {
        Path root=Files.createTempDirectory("blockwire-tls-contract-");
        try {
            var a=TlsIdentity.load(root.resolve("a"));var b=TlsIdentity.load(root.resolve("b"));
            check(!Arrays.equals(a.certificate().getEncoded(),b.certificate().getEncoded()),"instance_certificate_uniqueness");
            check(!Arrays.equals(a.certificate().getPublicKey().getEncoded(),b.certificate().getPublicKey().getEncoded()),"instance_key_uniqueness");
            var persisted=TlsIdentity.load(root.resolve("a"));
            check(Arrays.equals(a.certificate().getEncoded(),persisted.certificate().getEncoded()),"certificate_persistence");
            a.certificate().checkValidity();a.certificate().verify(a.certificate().getPublicKey());checks++;
            check(a.certificate().getBasicConstraints()==-1,"certificate_is_not_ca");
            check(a.certificate().getExtendedKeyUsage().contains("1.3.6.1.5.5.7.3.1"),"server_auth_only");
            check(a.certificate().getSubjectAlternativeNames().stream().anyMatch(n->n.get(1).equals(TlsIdentity.TLS_NAME)),"stable_tls_service_name");
            check(a.certificate().getPublicKey().getAlgorithm().equals("EC"),"native_ec_key");
            if(FileSystems.getDefault().supportedFileAttributeViews().contains("posix")) {
                for(String file:List.of("identity.p12","certificate.pem"))
                    check(Files.getPosixFilePermissions(root.resolve("a/tls/"+file)).equals(
                        PosixFilePermissions.fromString("rw-------")),"private_tls_"+file);
                check(Files.getPosixFilePermissions(root.resolve("a/tls")).equals(
                    PosixFilePermissions.fromString("rwx------")),"private_tls_directory");
            }
            Files.delete(a.certificateFile());
            check(Arrays.equals(a.certificate().getEncoded(),TlsIdentity.load(root.resolve("a")).certificate().getEncoded()),"recover_missing_export_without_rotation");
            Files.write(a.certificateFile(),Files.readAllBytes(b.certificateFile()));
            refused(()->TlsIdentity.load(root.resolve("a")),"export_mismatch_fails_closed");
            // Existing public trust must never cause silent replacement of a missing private identity.
            Files.delete(root.resolve("b/tls/identity.p12"));
            refused(()->TlsIdentity.load(root.resolve("b")),"missing_private_key_fails_closed");
            var c=TlsIdentity.load(root.resolve("c"));byte[] publicBefore=Files.readAllBytes(c.certificateFile());
            Files.writeString(root.resolve("c/tls/identity.p12"),"corrupt");
            refused(()->TlsIdentity.load(root.resolve("c")),"corrupt_identity_fails_closed");
            check(Arrays.equals(publicBefore,Files.readAllBytes(c.certificateFile())),"corruption_does_not_change_trust");
            var expired=TlsIdentity.load(root.resolve("expired"));
            var expiredStore=KeyStore.getInstance("PKCS12");
            try(var input=Files.newInputStream(root.resolve("expired/tls/identity.p12"))){expiredStore.load(input,new char[0]);}
            var privateKey=(PrivateKey)expiredStore.getKey("instance",new char[0]);
            var expiredBuilder=new org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder(
                expired.certificate(),expired.certificate().getSerialNumber(),
                new Date(System.currentTimeMillis()-172800000),new Date(System.currentTimeMillis()-86400000),
                expired.certificate().getSubjectX500Principal(),expired.certificate().getPublicKey());
            expiredBuilder.addExtension(org.bouncycastle.asn1.x509.Extension.basicConstraints,true,new org.bouncycastle.asn1.x509.BasicConstraints(false));
            expiredBuilder.addExtension(org.bouncycastle.asn1.x509.Extension.extendedKeyUsage,false,
                new org.bouncycastle.asn1.x509.ExtendedKeyUsage(org.bouncycastle.asn1.x509.KeyPurposeId.id_kp_serverAuth));
            var expiredSigner=new org.bouncycastle.operator.jcajce.JcaContentSignerBuilder("SHA256withECDSA")
                .setProvider(new org.bouncycastle.jce.provider.BouncyCastleProvider()).build(privateKey);
            var expiredCertificate=new org.bouncycastle.cert.jcajce.JcaX509CertificateConverter().getCertificate(expiredBuilder.build(expiredSigner));
            expiredStore.setKeyEntry("instance",privateKey,new char[0],new java.security.cert.Certificate[]{expiredCertificate});
            try(var output=Files.newOutputStream(root.resolve("expired/tls/identity.p12"))){expiredStore.store(output,new char[0]);}
            Files.writeString(expired.certificateFile(),"-----BEGIN CERTIFICATE-----\n"+
                Base64.getMimeEncoder(64,new byte[]{'\n'}).encodeToString(expiredCertificate.getEncoded())+"\n-----END CERTIFICATE-----\n");
            try {TlsIdentity.load(root.resolve("expired"));throw new AssertionError("expired_certificate_fails_closed");}
            catch(java.io.IOException error) {check(error.getCause() instanceof CertificateExpiredException,"expired_certificate_fails_closed");}
            // An interrupted initial write must not become an identity or block a fresh atomic write.
            Files.createDirectories(root.resolve("interrupted/tls"));
            Files.writeString(root.resolve("interrupted/tls/.identity.p12-unfinished.tmp"),"partial");
            check(TlsIdentity.load(root.resolve("interrupted")).certificate()!=null,"interrupted_temp_not_promoted");
            if(FileSystems.getDefault().supportedFileAttributeViews().contains("posix")) {
                Files.createDirectories(root.resolve("symlink"));
                Files.createSymbolicLink(root.resolve("symlink/tls"),root.resolve("c/tls"));
                refused(()->TlsIdentity.load(root.resolve("symlink")),"tls_symlink_rejected");
            }
        } finally {deleteTree(root);}
        System.out.println("BLOCKWIRE_TLS_CONTRACT_PASS checks="+checks);
    }
}
