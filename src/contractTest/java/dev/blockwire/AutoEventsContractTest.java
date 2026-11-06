package dev.blockwire;

import com.google.gson.*;
/** Protocol boundaries, not a graphical chat/entity integration claim. */
public final class AutoEventsContractTest {
    private static int checks;
    private static JsonObject request(String text) {
        var q=new JsonObject();q.addProperty("op","chat");q.addProperty("message",text);q.addProperty("actor_session","actor");return q;
    }
    public static void main(String[] args) {
        if(!Protocol.chat(request("Hello 😀")).equals("Hello 😀"))throw new AssertionError("chat_text_exact");checks++;
        for(String text:new String[]{""," ","/kill","  /kill","x\nstop","x\rstop","x\u0000","x§a","x\u2028","x\ud800","x".repeat(257)}) {
            try{Protocol.chat(request(text));throw new AssertionError("unsafe_chat_accepted");}catch(IllegalArgumentException expected){checks++;}
        }
        var q=request("hello");q.remove("actor_session");
        try{Protocol.chat(q);throw new AssertionError("chat_requires_actor");}catch(IllegalArgumentException expected){checks++;}
        q=request("hello");q.addProperty("recipient","other");
        try{Protocol.chat(q);throw new AssertionError("no_host_routing");}catch(IllegalArgumentException expected){checks++;}
        if(AutoEvents.MAX_ENTITIES!=16 || AutoEvents.MAX_SCAN!=256 || AutoEvents.MAX_CHAT!=2048)throw new AssertionError("bounded_source");checks++;
        System.out.println("Auto-event protocol contracts PASS: "+checks);
    }
}
