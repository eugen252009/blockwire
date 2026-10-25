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
    public static JsonObject ok(String text) {var o=new JsonObject();o.addProperty("text",text);return o;}
}
