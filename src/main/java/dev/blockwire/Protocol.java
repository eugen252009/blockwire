package dev.blockwire;

import com.google.gson.*;
import java.util.Set;

/** Strict flat command envelopes: reject typos and invalid values before any game effect. */
public final class Protocol {
    private Protocol() {}
    public static String operation(JsonObject request) { return string(request,"op"); }
    public static void fields(JsonObject request,String... fields) {
        var allowed=new java.util.HashSet<>(Set.of(fields));allowed.add("op");allowed.add("id");
        for(String key:request.keySet()) if(!allowed.contains(key))throw new IllegalArgumentException("unknown_field: "+key);
    }
    public static String string(JsonObject o,String key) {
        JsonElement v=o.get(key);
        if(v==null || !v.isJsonPrimitive() || !v.getAsJsonPrimitive().isString())throw new IllegalArgumentException("expected_string: "+key);
        return v.getAsString();
    }
    public static double number(JsonObject o,String key,double min,double max) {
        JsonElement v=o.get(key);
        if(v==null || !v.isJsonPrimitive() || !v.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("expected_number: "+key);
        double n=v.getAsDouble();
        if(!Double.isFinite(n) || n<min || n>max)throw new IllegalArgumentException("out_of_range: "+key);
        return n;
    }
    public static int integer(JsonObject o,String key,int min,int max) {
        double n=number(o,key,min,max);
        if(n!=Math.rint(n))throw new IllegalArgumentException("expected_integer: "+key);
        return (int)n;
    }
    /** Optional attack identity guard: never allow a target guard on use or without a session fence. */
    public static Integer actionTarget(JsonObject q) {
        fields(q,"name","actor_session","target_entity_id");
        String name=string(q,"name");
        if(!Set.of("attack","use").contains(name))throw new IllegalArgumentException("unsupported_action");
        if(q.has("actor_session"))string(q,"actor_session");
        if(!q.has("target_entity_id"))return null;
        if(!name.equals("attack") || !q.has("actor_session"))throw new IllegalArgumentException("target_guard_requires_attack_session");
        return integer(q,"target_entity_id",0,Integer.MAX_VALUE);
    }
    public static void requireTarget(Integer expected,Integer actual) {
        if(expected!=null && !expected.equals(actual))throw new IllegalStateException("target_entity_changed");
    }
    public static JsonObject ok(String text) {var o=new JsonObject();o.addProperty("text",text);return o;}
}
