package dev.blockwire;

import com.google.gson.*;
import io.netty.util.NetUtil;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.SecureRandom;
import java.util.HexFormat;

/** Local config is the authority for startup, listener address and API key. */
public record BridgeConfig(boolean enabled,String serverIp,int port,String apiKey) {
    /** Keep existing instance credentials/identity in place; never merge two authorities. */
    public static Path directory(Path minecraftConfig) throws java.io.IOException {
        Path current=minecraftConfig.resolve("blockwire"),legacy=minecraftConfig.resolve("block-bridge");
        boolean hasCurrent=Files.exists(current,LinkOption.NOFOLLOW_LINKS);
        boolean hasLegacy=Files.exists(legacy,LinkOption.NOFOLLOW_LINKS);
        if(hasCurrent && hasLegacy)throw new java.io.IOException("ambiguous_blockwire_and_legacy_config");
        return hasLegacy?legacy:current;
    }
    public static BridgeConfig parse(JsonObject settings) {
        for(String name:settings.keySet())
            if(!java.util.Set.of("enabled","server_ip","port","mcp_api_key").contains(name))
                throw new IllegalArgumentException("unknown_config_field");
        JsonElement enabled=settings.get("enabled");
        if(enabled==null || !enabled.isJsonPrimitive() || !enabled.getAsJsonPrimitive().isBoolean())
            throw new IllegalArgumentException("invalid_enabled");
        String ip=Protocol.string(settings,"server_ip");
        if(!NetUtil.isValidIpV4Address(ip) && !NetUtil.isValidIpV6Address(ip))
            throw new IllegalArgumentException("server_ip_must_be_literal_ip");
        int port=Protocol.integer(settings,"port",1024,65535);
        String key=Protocol.string(settings,"mcp_api_key");
        if(!key.matches("[A-Za-z0-9_-]{32,256}"))throw new IllegalArgumentException("invalid_mcp_api_key");
        return new BridgeConfig(enabled.getAsBoolean(),ip,port,key);
    }
    public static BridgeConfig load(Path dir) throws java.io.IOException {
        if(Files.isSymbolicLink(dir))throw new java.io.IOException("symlink_directory");
        Files.createDirectories(dir);
        permissions(dir,"rwx------");
        Path file=dir.resolve("settings.json"),legacy=dir.resolve("token");
        if(Files.isSymbolicLink(file) || Files.isSymbolicLink(legacy))throw new java.io.IOException("symlink_config");
        var json=Files.exists(file)?JsonParser.parseString(Files.readString(file)).getAsJsonObject():new JsonObject();
        boolean changed=false;
        if(!json.has("enabled")){json.addProperty("enabled",false);changed=true;}
        if(!json.has("server_ip")){json.addProperty("server_ip","127.0.0.1");changed=true;}
        if(!json.has("port")){json.addProperty("port",8765);changed=true;}
        if(!json.has("mcp_api_key")){
            String key;
            if(Files.exists(legacy))key=Files.readString(legacy).strip();
            else {byte[] bytes=new byte[32];new SecureRandom().nextBytes(bytes);key=HexFormat.of().formatHex(bytes);}
            json.addProperty("mcp_api_key",key);changed=true;
        }
        BridgeConfig config=parse(json); // Validate everything before persisting/migrating.
        if(!Files.exists(file))privateFile(file);
        permissions(file,"rw-------");
        if(changed)Files.writeString(file,new GsonBuilder().setPrettyPrinting().create().toJson(json)+"\n");
        // Compatibility with the initial Python token-file interface. Config remains authoritative.
        if(!Files.exists(legacy))privateFile(legacy);
        permissions(legacy,"rw-------");Files.writeString(legacy,config.apiKey()+"\n");
        return config;
    }
    private static void privateFile(Path path) throws java.io.IOException {
        try {Files.createFile(path,PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rw-------")));}
        catch(UnsupportedOperationException e){Files.createFile(path);}
    }
    private static void permissions(Path path,String value) throws java.io.IOException {
        try {Files.setPosixFilePermissions(path,PosixFilePermissions.fromString(value));}
        catch(UnsupportedOperationException ignored) {}
    }
}
