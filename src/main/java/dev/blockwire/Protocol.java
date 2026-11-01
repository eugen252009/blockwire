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
    public static boolean bool(JsonObject o,String key,boolean fallback) {
        if(!o.has(key))return fallback;
        var v=o.get(key);
        if(!v.isJsonPrimitive() || !v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("expected_boolean: "+key);
        return v.getAsBoolean();
    }
    public static int integer(JsonObject o,String key,int min,int max) {
        double n=number(o,key,min,max);
        if(n!=Math.rint(n))throw new IllegalArgumentException("expected_integer: "+key);
        return (int)n;
    }
    /** Optional time-based camera request; omitted duration preserves legacy immediate look. */
    public static Integer rotationDuration(JsonObject q) {
        if(!q.has("duration_ms")) {
            if(q.has("rotation_profile"))throw new IllegalArgumentException("rotation_profile_requires_duration");
            return null;
        }
        return integer(q,"duration_ms",1,RotationController.MAX_DURATION_MS);
    }
    public static String rotationProfile(JsonObject q) {
        if(!q.has("rotation_profile"))return "smoothstep";
        String profile=string(q,"rotation_profile");
        if(!Set.of("linear","smoothstep").contains(profile))throw new IllegalArgumentException("unsupported_rotation_profile");
        return profile;
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
    /** Each key may shorten, never extend, the enclosing bounded hold. */
    public static java.util.Map<String,Integer> buttonTicks(JsonObject q,Set<String> buttons,int ticks) {
        var result=new java.util.HashMap<String,Integer>();
        if(!q.has("button_ticks")){buttons.forEach(key->result.put(key,ticks));return java.util.Map.copyOf(result);}
        if(!q.get("button_ticks").isJsonObject())throw new IllegalArgumentException("expected_button_ticks_object");
        var values=q.getAsJsonObject("button_ticks");
        if(!buttons.containsAll(values.keySet()))throw new IllegalArgumentException("button_ticks_keys_must_be_held_buttons");
        for(String key:values.keySet())result.put(key,integer(values,key,1,ticks));
        return java.util.Map.copyOf(result);
    }
    /** Legacy selection is unchanged; autonomous selection can fence the actor. */
    public static int hotbarSlot(JsonObject q) {
        fields(q,"slot","actor_session");
        if(q.has("actor_session"))string(q,"actor_session");
        return integer(q,"slot",0,8);
    }
    /** Optional session fence on native inventory operations; old envelopes remain valid. */
    public static void inventoryFields(JsonObject q,String... names) {
        var allowed=new java.util.ArrayList<String>(java.util.List.of(names));allowed.add("actor_session");
        fields(q,allowed.toArray(String[]::new));
        if(q.has("actor_session"))string(q,"actor_session");
    }
    /** One explicit slash command, bounded like native chat; never trim or split it. */
    public static String command(JsonObject q) {
        fields(q,"command","actor_session");
        if(q.has("actor_session"))string(q,"actor_session");
        String text=string(q,"command");
        if(text.length()<2 || text.length()>256 || text.charAt(0)!='/' ||
            text.charAt(1)=='/' || Character.isWhitespace(text.charAt(1)) || Character.isSpaceChar(text.charAt(1)))
            throw new IllegalArgumentException("expected_slash_command_max_256");
        for(int i=0;i<text.length();i++) {
            char c=text.charAt(i);
            if(Character.isISOControl(c) || c=='§' || c=='\u2028' || c=='\u2029' ||
                (Character.isSurrogate(c) && !(Character.isHighSurrogate(c) &&
                    i+1<text.length() && Character.isLowSurrogate(text.charAt(++i)))))
                throw new IllegalArgumentException("invalid_command_character");
        }
        return text.substring(1);
    }
    public static void requireTarget(Integer expected,Integer actual) {
        if(expected!=null && !expected.equals(actual))throw new IllegalStateException("target_entity_changed");
    }
    public static JsonObject ok(String text) {var o=new JsonObject();o.addProperty("text",text);return o;}
}
