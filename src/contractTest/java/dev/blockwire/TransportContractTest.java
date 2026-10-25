package dev.blockwire;

import com.google.gson.*;
import java.net.*;
import java.net.http.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class TransportContractTest {
    private static int checks;
    private static javax.net.ssl.SSLContext clientTls;
    private static void check(boolean condition,String label) {
        if(!condition)throw new AssertionError(label);checks++;
    }
    private static void rejected(Runnable action,String label) {
        try {action.run();throw new AssertionError(label);}
        catch(IllegalArgumentException expected){checks++;}
    }
    private static final class Inbox implements WebSocket.Listener {
        final BlockingQueue<String> messages=new LinkedBlockingQueue<>();
        final StringBuilder parts=new StringBuilder();
        public void onOpen(WebSocket socket){socket.request(1);}
        public CompletionStage<?> onText(WebSocket socket,CharSequence text,boolean last) {
            parts.append(text);if(last){messages.add(parts.toString());parts.setLength(0);}socket.request(1);return null;
        }
        JsonObject read() throws Exception {
            String message=messages.poll(3,TimeUnit.SECONDS);
            if(message==null)throw new AssertionError("response_timeout");
            return JsonParser.parseString(message).getAsJsonObject();
        }
    }
    private static WebSocket connect(int port,String token,String origin,String path,Inbox inbox) {
        var builder=HttpClient.newBuilder().sslContext(clientTls).build().newWebSocketBuilder().header("Authorization","Bearer "+token);
        if(origin!=null)builder.header("Origin",origin);
        return builder.buildAsync(URI.create("wss://127.0.0.1:"+port+path),inbox).join();
    }
    private static void deny(int port,String token,String origin,String path,int status,String label) {
        try {var ws=connect(port,token,origin,path,new Inbox());ws.abort();throw new AssertionError(label);}
        catch(CompletionException e) {
            check(e.getCause() instanceof WebSocketHandshakeException &&
                ((WebSocketHandshakeException)e.getCause()).getResponse().statusCode()==status,label);
        }
    }
    private static void until(java.util.function.BooleanSupplier condition) throws Exception {
        long end=System.nanoTime()+3_000_000_000L;
        while(!condition.getAsBoolean() && System.nanoTime()<end)Thread.sleep(10);
        check(condition.getAsBoolean(),"eventual_cleanup");
    }
    public static void main(String[] args) throws Exception {
        var q=new JsonObject();q.addProperty("op","look");q.addProperty("yaw",0);q.addProperty("pitch",-90);
        Protocol.fields(q,"yaw","pitch");
        check(Protocol.number(q,"yaw",0,180)==0,"inclusive_min");
        check(Protocol.integer(q,"pitch",-90,90)==-90,"negative_boundary");
        q.addProperty("pitch",90);check(Protocol.integer(q,"pitch",-90,90)==90,"inclusive_max");
        q.addProperty("pitch",90.1);rejected(()->Protocol.number(q,"pitch",-90,90),"reject_out_of_range");
        q.addProperty("pitch",0.5);rejected(()->Protocol.integer(q,"pitch",-90,90),"reject_fraction");
        q.addProperty("pitch",Double.NaN);rejected(()->Protocol.number(q,"pitch",-90,90),"reject_nan");
        q.addProperty("pitch",Double.POSITIVE_INFINITY);rejected(()->Protocol.number(q,"pitch",-90,90),"reject_infinite");
        q.addProperty("pitch","1");rejected(()->Protocol.number(q,"pitch",-90,90),"reject_numeric_string");
        q.addProperty("typo",1);rejected(()->Protocol.fields(q,"yaw","pitch"),"reject_unknown_fields");

        check(MenuInput.mouseButton(0)==com.mojang.blaze3d.platform.InputConstants.MOUSE_BUTTON_LEFT,"native_left_button");
        check(MenuInput.mouseButton(1)==com.mojang.blaze3d.platform.InputConstants.MOUSE_BUTTON_RIGHT,"native_right_button");
        rejected(()->MenuInput.mouseButton(2),"reject_middle_button");
        check(MenuInput.selectAll().isSelectAll(),"native_select_all_shortcut");
        check(MenuInput.key(com.mojang.blaze3d.platform.InputConstants.KEY_BACKSPACE,0).shortcutKey()==8,"native_logical_backspace");
        check(MenuInput.key(com.mojang.blaze3d.platform.InputConstants.KEY_LEFT,0).shortcutKey()==1073741904,"native_logical_left");
        check(MenuInput.key(com.mojang.blaze3d.platform.InputConstants.KEY_RETURN,0).isConfirmation(),"native_enter_scancode");
        var heldKey=new net.minecraft.client.KeyMapping("blockwire.test.hold",com.mojang.blaze3d.platform.InputConstants.Type.KEYBOARD,
            com.mojang.blaze3d.platform.InputConstants.KEY_W,net.minecraft.client.KeyMapping.Category.MISC);
        InputState.set(heldKey,true);check(heldKey.isDown(),"hold_mapping_down");
        InputState.set(heldKey,false);check(!heldKey.isDown(),"hold_mapping_up");
        var toggleKey=new net.minecraft.client.ToggleKeyMapping("blockwire.test.toggle",
            com.mojang.blaze3d.platform.InputConstants.KEY_W,net.minecraft.client.KeyMapping.Category.MISC,()->true,false);
        InputState.set(toggleKey,true);check(toggleKey.isDown(),"toggle_mapping_down");
        InputState.set(toggleKey,true);check(toggleKey.isDown(),"reapply_does_not_toggle_off");
        InputState.set(toggleKey,false);check(!toggleKey.isDown(),"toggle_mapping_released");
        var settings=new JsonObject();
        settings.addProperty("enabled",true);settings.addProperty("server_ip","127.0.0.1");
        settings.addProperty("port",8877);settings.addProperty("mcp_api_key","Custom_key-".repeat(4));
        var config=BridgeConfig.parse(settings);
        check(config.enabled() && config.port()==8877 && config.apiKey().equals("Custom_key-".repeat(4)),"configured_startup_authority");
        settings.addProperty("server_ip","0.0.0.0");
        check(BridgeConfig.parse(settings).serverIp().equals("0.0.0.0"),"explicit_wildcard_bind_allowed");
        settings.addProperty("server_ip","::1");
        check(BridgeConfig.parse(settings).serverIp().equals("::1"),"ipv6_config_allowed");
        settings.addProperty("server_ip","localhost");
        rejected(()->BridgeConfig.parse(settings),"reject_dns_bind");
        settings.addProperty("server_ip","127.0.0.1");settings.addProperty("mcp_api_key","short");
        rejected(()->BridgeConfig.parse(settings),"reject_weak_config_key");
        settings.addProperty("mcp_api_key","b".repeat(32));settings.addProperty("enabled","true");
        rejected(()->BridgeConfig.parse(settings),"reject_string_enabled");
        settings.addProperty("enabled",true);settings.addProperty("port",65536);
        rejected(()->BridgeConfig.parse(settings),"reject_invalid_port");
        settings.addProperty("port",8765);settings.addProperty("typo",true);
        rejected(()->BridgeConfig.parse(settings),"reject_config_typo");

        var folder=java.nio.file.Files.createTempDirectory("blockwire-config-");
        try {
            var fresh=BridgeConfig.load(folder);
            check(!fresh.enabled() && fresh.serverIp().equals("127.0.0.1") && fresh.apiKey().matches("[0-9a-f]{64}"),"safe_generated_defaults");
            var original=fresh.apiKey();
            check(BridgeConfig.load(folder).apiKey().equals(original),"config_key_persistence");
            java.nio.file.Files.writeString(folder.resolve("settings.json"),"{\"port\":8877}");
            var migrated=BridgeConfig.load(folder);
            check(!migrated.enabled() && migrated.port()==8877 && migrated.apiKey().equals(original),"legacy_migration_preserves_key");
            if(java.nio.file.FileSystems.getDefault().supportedFileAttributeViews().contains("posix"))
                check(java.nio.file.Files.getPosixFilePermissions(folder.resolve("settings.json")).equals(
                    java.nio.file.attribute.PosixFilePermissions.fromString("rw-------")),"private_config_permissions");
        } finally {
            try(var files=java.nio.file.Files.walk(folder)){for(var file:files.sorted(java.util.Comparator.reverseOrder()).toList())java.nio.file.Files.delete(file);}
        }
        var compatibility=java.nio.file.Files.createTempDirectory("blockwire-rename-");
        try {
            check(BridgeConfig.directory(compatibility).equals(compatibility.resolve("blockwire")),"new_brand_config_directory");
            var legacy=compatibility.resolve("block-bridge");
            var before=BridgeConfig.load(legacy);var identity=TlsIdentity.load(legacy);
            check(BridgeConfig.directory(compatibility).equals(legacy),"legacy_config_selected_without_copy");
            check(BridgeConfig.load(BridgeConfig.directory(compatibility)).apiKey().equals(before.apiKey()),"rename_preserves_api_key");
            check(java.util.Arrays.equals(identity.certificate().getEncoded(),TlsIdentity.load(BridgeConfig.directory(compatibility)).certificate().getEncoded()),"rename_preserves_tls_identity");
            check(!java.nio.file.Files.exists(compatibility.resolve("blockwire")),"legacy_use_does_not_create_duplicate_config");
            java.nio.file.Files.createDirectory(compatibility.resolve("blockwire"));
            try {BridgeConfig.directory(compatibility);throw new AssertionError("ambiguous_config_must_fail_closed");}
            catch(java.io.IOException expected){checks++;}
        } finally {TlsContractTest.deleteTree(compatibility);}
        String token="a".repeat(64);
        var effects=new AtomicInteger();var releases=new AtomicInteger();
        var game=Executors.newSingleThreadExecutor(r->new Thread(r,"fake-game-thread"));
        var tlsDirectory=java.nio.file.Files.createTempDirectory("blockwire-transport-tls-");
        var identity=TlsIdentity.load(tlsDirectory);
        clientTls=TlsContractTest.trust(identity.certificate());
        try(var server=new BridgeServer(0,token,identity.context(),game,request->{
            check(Thread.currentThread().getName().equals("fake-game-thread"),"game_thread_dispatch");
            String op=Protocol.operation(request);Protocol.fields(request);
            if(!op.equals("increment"))throw new IllegalArgumentException("unknown_operation");
            var result=new JsonObject();result.addProperty("value",effects.incrementAndGet());return result;
        },()->{
            check(Thread.currentThread().getName().equals("fake-game-thread"),"game_thread_release");releases.incrementAndGet();
        })) {
            int port=server.port();
            deny(port,"b".repeat(64),null,"/v1",403,"reject_unauthorized");
            deny(port,token,"https://example.invalid","/v1",403,"reject_browser_origin");
            deny(port,token,null,"/bad",403,"reject_wrong_endpoint");
            var inbox=new Inbox();var ws=connect(port,token,null,"/v1",inbox);
            deny(port,token,null,"/v1",409,"exclusive_controller");
            ws.sendText("{\"id\":1,\"op\":\"increment\"}",true).join();
            var response=inbox.read();check(response.get("ok").getAsBoolean() && response.get("id").getAsInt()==1 &&
                response.getAsJsonObject("result").get("value").getAsInt()==1,"authenticated_request");
            ws.sendText("{\"id\":2,\"op\":\"increment\",\"typo\":true}",true).join();
            check(!inbox.read().get("ok").getAsBoolean() && effects.get()==1,"error_before_effect");
            ws.sendText("{\"id\":3,\"op\":\"unknown\"}",true).join();
            check(!inbox.read().get("ok").getAsBoolean() && effects.get()==1,"unknown_operation_no_effect");
            ws.sendClose(1000,"done").join();until(()->releases.get()==1);
            var next=new Inbox();var ws2=connect(port,token,null,"/v1",next);
            ws2.sendText("{\"op\":\"increment\"}",true).join();
            until(()->releases.get()==2);check(effects.get()==1,"missing_id_no_effect");

            var third=new Inbox();var ws3=connect(port,token,null,"/v1",third);
            var blocked=new CountDownLatch(1);var entered=new CountDownLatch(1);
            game.submit(()->{entered.countDown();try{blocked.await();}catch(InterruptedException e){Thread.currentThread().interrupt();}});
            entered.await();
            ws3.sendText("{\"id\":4,\"op\":\"increment\"}",true).join();
            Thread.sleep(100);ws3.abort();Thread.sleep(100);blocked.countDown();
            until(()->releases.get()==3);
            check(effects.get()==1,"disconnected_queued_command_no_effect");

            var fourth=new Inbox();var ws4=connect(port,token,null,"/v1",fourth);
            var delay=new CountDownLatch(1);
            game.submit(()->{try{delay.await();}catch(InterruptedException e){Thread.currentThread().interrupt();}});
            ws4.sendText("{\"id\":5,\"op\":\"increment\"}",true).join();
            Thread.sleep(2200);delay.countDown();
            var expired=fourth.read();
            check(!expired.get("ok").getAsBoolean() && expired.get("error").getAsString().equals("expired_request") &&
                effects.get()==1,"expired_queued_command_no_effect");
            ws4.abort();until(()->releases.get()==4);
        } finally {
            game.shutdownNow();game.awaitTermination(3,TimeUnit.SECONDS);
            TlsContractTest.deleteTree(tlsDirectory);
        }
        System.out.println("BLOCKWIRE_CONTRACT_PASS checks="+checks);
    }
}
