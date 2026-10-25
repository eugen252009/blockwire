package dev.blockwire;

import com.google.gson.*;
import java.nio.file.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Isolated real TLS socket for cross-language tests; never a gameplay substitute. */
public final class TlsFixture {
    public static void main(String[] args) throws Exception {
        Path root=Path.of(args[0]);var identity=TlsIdentity.load(root.resolve("instance"));
        var other=TlsIdentity.load(root.resolve("other"));
        var executor=Executors.newSingleThreadExecutor();var calls=new AtomicInteger();
        try(var server=new BridgeServer(0,"a".repeat(64),identity.context(),executor,request->{
            var reply=Protocol.ok("TLS fixture, not Minecraft gameplay.");
            reply.addProperty("calls",calls.incrementAndGet());return reply;
        },()->{})) {
            var ready=new JsonObject();ready.addProperty("url","wss://127.0.0.1:"+server.port()+"/v1");
            ready.addProperty("certificate",identity.certificateFile().toString());
            ready.addProperty("wrong_certificate",other.certificateFile().toString());
            Files.writeString(root.resolve("ready.json"),ready.toString());
            while(Files.exists(root.resolve("running")))Thread.sleep(50);
        } finally {executor.shutdownNow();executor.awaitTermination(3,TimeUnit.SECONDS);}
    }
}
