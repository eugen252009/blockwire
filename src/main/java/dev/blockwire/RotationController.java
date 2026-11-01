package dev.blockwire;

import com.google.gson.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;

/** One actor-bound time-based camera plan. Native ticks apply orientation; it never owns movement keys. */
public final class RotationController {
    public static final int MAX_DURATION_MS=5000;
    private static final double EPSILON=.0001;

    public record Angles(double yaw,double pitch) {}
    private static final class State {
        long id,startedNs,finishedNs,durationNs;
        double startYaw,startPitch,targetYaw,targetPitch,appliedTargetYaw,terminalYaw,terminalPitch;
        String profile,status,reason;
        boolean active;
    }

    private LocalPlayer actor;
    private ClientLevel level;
    private State current,previous;
    private long nextId=1;

    public static double normalizeYaw(double yaw) {return (yaw+180.)%360.+(yaw+180.<0?360.:0.)-180.;}
    public static double yawDelta(double target,double current) {return normalizeYaw(target-current);}
    public static double clampPitch(double pitch) {return Math.max(-90.,Math.min(90.,pitch));}
    public static double curve(String profile,double fraction) {
        double t=Math.max(0.,Math.min(1.,fraction));
        if(profile.equals("linear"))return t;
        if(profile.equals("smoothstep"))return t*t*(3.-2.*t);
        throw new IllegalArgumentException("unsupported_rotation_profile");
    }
    public static Angles interpolate(double startYaw,double startPitch,double targetYaw,double targetPitch,String profile,double fraction) {
        double progress=curve(profile,fraction);
        return new Angles(startYaw+yawDelta(targetYaw,startYaw)*progress,
            startPitch+(clampPitch(targetPitch)-startPitch)*progress);
    }

    private static boolean same(State state,double yaw,double pitch,int durationMs,String profile) {
        return state!=null && state.active && Math.abs(yawDelta(yaw,state.targetYaw))<EPSILON &&
            Math.abs(clampPitch(pitch)-state.targetPitch)<EPSILON && state.durationNs==durationMs*1_000_000L &&
            state.profile.equals(profile);
    }
    private static void apply(LocalPlayer actor,Angles angles) {
        actor.setYRot((float)angles.yaw());actor.setXRot((float)angles.pitch());
    }
    private void finish(String status,String reason,long now) {
        if(current==null || !current.active)return;
        current.active=false;current.status=status;current.reason=reason;current.finishedNs=now;
        current.terminalYaw=actor==null?current.startYaw:actor.getYRot();
        current.terminalPitch=actor==null?current.startPitch:actor.getXRot();
    }
    private JsonObject state(State state,long now) {
        var out=new JsonObject();
        if(state==null){out.addProperty("status","idle");out.addProperty("active",false);return out;}
        out.addProperty("rotation_id",state.id);out.addProperty("status",state.status);out.addProperty("active",state.active);
        out.addProperty("profile",state.profile);out.addProperty("requested_duration_ms",state.durationNs/1_000_000L);
        out.addProperty("started_ns",state.startedNs);out.addProperty("elapsed_ms",Math.max(0.,(Math.min(now,state.finishedNs==0?now:state.finishedNs)-state.startedNs)/1_000_000.));
        out.addProperty("start_yaw",state.startYaw);out.addProperty("start_pitch",state.startPitch);
        out.addProperty("target_yaw",state.targetYaw);out.addProperty("target_pitch",state.targetPitch);
        out.addProperty("applied_target_yaw",state.appliedTargetYaw);
        double yaw=state.active && actor!=null?actor.getYRot():state.terminalYaw;
        double pitch=state.active && actor!=null?actor.getXRot():state.terminalPitch;
        out.addProperty("current_yaw",yaw);out.addProperty("current_pitch",pitch);
        out.addProperty("yaw_error",Math.abs(yawDelta(state.targetYaw,yaw)));out.addProperty("pitch_error",Math.abs(state.targetPitch-pitch));
        if(state.finishedNs!=0)out.addProperty("actual_duration_ms",(state.finishedNs-state.startedNs)/1_000_000.);
        if(state.reason!=null)out.addProperty("reason",state.reason);
        return out;
    }
    private JsonObject receipt(State state,Long superseded,boolean reused) {
        var out=Protocol.ok(state.active?
            "Time-based native camera rotation scheduled; observe rotation state and final orientation.":
            "Camera already matched the requested orientation.");
        out.addProperty("scheduled",state.active);out.addProperty("rotation_id",state.id);
        out.addProperty("status",state.status);out.addProperty("started_ns",state.startedNs);
        out.addProperty("requested_duration_ms",state.durationNs/1_000_000L);out.addProperty("profile",state.profile);
        out.addProperty("target_yaw",state.targetYaw);out.addProperty("target_pitch",state.targetPitch);
        if(superseded!=null)out.addProperty("superseded_rotation_id",superseded);
        if(reused)out.addProperty("reused_active_rotation",true);
        return out;
    }

    public JsonObject schedule(Minecraft mc,double yaw,double pitch,int durationMs,String profile) {
        long now=System.nanoTime();double targetYaw=normalizeYaw(yaw),targetPitch=clampPitch(pitch);
        if(same(current,targetYaw,targetPitch,durationMs,profile))return receipt(current,null,true);
        Long superseded=null;
        if(current!=null) {
            if(current.active){superseded=current.id;finish("superseded","new_rotation_target",now);}
            previous=current;
        }
        actor=mc.player;level=mc.level;
        var state=new State();state.id=nextId++;state.startedNs=now;state.durationNs=durationMs*1_000_000L;
        state.startYaw=actor.getYRot();state.startPitch=actor.getXRot();state.targetYaw=targetYaw;state.targetPitch=targetPitch;
        state.appliedTargetYaw=state.startYaw+yawDelta(targetYaw,state.startYaw);state.profile=profile;state.status="active";state.active=true;
        current=state;
        if(Math.abs(yawDelta(targetYaw,state.startYaw))<EPSILON && Math.abs(targetPitch-state.startPitch)<EPSILON) {
            apply(actor,new Angles(state.appliedTargetYaw,targetPitch));finish("completed","already_at_target",now);
        }
        return receipt(state,superseded,false);
    }

    public JsonObject immediate(Minecraft mc,double yaw,double pitch) {
        long now=System.nanoTime();Long superseded=null;
        if(current!=null) {
            if(current.active){superseded=current.id;finish("superseded","immediate_rotation",now);}
            previous=current;
        }
        actor=mc.player;level=mc.level;
        var state=new State();state.id=nextId++;state.startedNs=now;state.finishedNs=now;state.durationNs=0;
        state.startYaw=actor.getYRot();state.startPitch=actor.getXRot();state.targetYaw=normalizeYaw(yaw);state.targetPitch=clampPitch(pitch);
        state.appliedTargetYaw=state.startYaw+yawDelta(state.targetYaw,state.startYaw);state.profile="instant";
        apply(actor,new Angles(state.appliedTargetYaw,state.targetPitch));state.terminalYaw=actor.getYRot();state.terminalPitch=actor.getXRot();
        state.status="completed";state.reason="legacy_immediate_request";current=state;
        var out=receipt(state,superseded,false);out.addProperty("legacy_immediate",true);return out;
    }

    public void tick(Minecraft mc,boolean authorityAvailable) {
        if(current==null || !current.active)return;
        long now=System.nanoTime();
        if(!authorityAvailable){finish("cancelled","controller_unavailable",now);return;}
        if(mc.player!=actor || mc.level!=level || actor==null){finish("actor_session_changed","actor_session_changed",now);return;}
        if(!actor.isAlive()){finish("cancelled","player_dead",now);return;}
        if(mc.gui.screen()!=null || mc.isPaused()){finish("cancelled","screen_or_pause",now);return;}
        double fraction=(double)(now-current.startedNs)/current.durationNs;
        var angles=interpolate(current.startYaw,current.startPitch,current.appliedTargetYaw,current.targetPitch,current.profile,fraction);
        apply(actor,angles);
        if(fraction>=1.){apply(actor,new Angles(current.appliedTargetYaw,current.targetPitch));finish("completed","target_reached",now);}
    }

    public void cancel(Minecraft mc,String reason) {
        if(current!=null && current.active)finish("cancelled",reason,System.nanoTime());
    }

    public JsonObject snapshot(Minecraft mc,String actorSession) {
        var out=new JsonObject();out.addProperty("profile","native_time_rotation_v1");out.addProperty("actor_session",actorSession);
        JsonObject selected=state(current,System.nanoTime());for(String key:selected.keySet())out.add(key,selected.get(key));
        if(previous!=null)out.add("previous",state(previous,previous.finishedNs));
        out.addProperty("time_base","System.nanoTime / client START tick");
        out.addProperty("text","Read-only camera-plan state; requested duration is quantized by actual client ticks and is not a completion receipt.");
        return out;
    }

    public void annotate(JsonObject sample) {
        State state=current;if(state==null)return;
        sample.addProperty("rotation_id",state.id);sample.addProperty("rotation_status",state.status);
        sample.addProperty("rotation_active",state.active);sample.addProperty("rotation_target_yaw",state.targetYaw);
        sample.addProperty("rotation_target_pitch",state.targetPitch);sample.addProperty("rotation_requested_duration_ms",state.durationNs/1_000_000L);
        sample.addProperty("rotation_profile",state.profile);
    }
}
