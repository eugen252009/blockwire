package dev.blockwire;

import com.google.gson.*;
import com.mojang.blaze3d.platform.InputConstants;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.components.*;
import net.minecraft.client.gui.components.events.*;
import net.minecraft.client.gui.navigation.ScreenRectangle;
import net.minecraft.client.gui.screens.*;
import net.minecraft.client.gui.screens.worldselection.WorldSelectionList;
import net.minecraft.client.input.*;
import java.util.*;

/** Native screen event routing. No direct button callbacks, commands, files or field mutation. */
public final class MenuBridge {
    private record Target(GuiEventListener listener,ScreenRectangle bounds) {}
    private Screen sampled;
    private int serial, width, height;
    private List<Target> targets=List.of();
    private static final Map<String,Integer> KEYS=Map.ofEntries(
        Map.entry("escape",InputConstants.KEY_ESCAPE),Map.entry("enter",InputConstants.KEY_RETURN),
        Map.entry("tab",InputConstants.KEY_TAB),Map.entry("up",InputConstants.KEY_UP),
        Map.entry("down",InputConstants.KEY_DOWN),Map.entry("left",InputConstants.KEY_LEFT),
        Map.entry("right",InputConstants.KEY_RIGHT),Map.entry("backspace",InputConstants.KEY_BACKSPACE),
        Map.entry("delete",InputConstants.KEY_DELETE),Map.entry("home",InputConstants.KEY_HOME),
        Map.entry("end",InputConstants.KEY_END),Map.entry("page_up",InputConstants.KEY_PAGEUP),
        Map.entry("page_down",InputConstants.KEY_PAGEDOWN),Map.entry("space",InputConstants.KEY_SPACE));
    private static String bounded(String text){return text.length()>240?text.substring(0,240):text;}
    private static void walk(GuiEventListener listener,ScreenRectangle clip,List<Target> result,Set<GuiEventListener> seen,int depth) {
        if(depth>16 || result.size()>=384 || !seen.add(listener))return;
        if(listener instanceof AbstractWidget widget && !widget.visible)return;
        var rect=listener.getRectangle();
        if(rect.width()>0 && rect.height()>0) {
            clip=rect.intersection(clip);
            if(clip==null || clip.width()<=0 || clip.height()<=0)return;
            result.add(new Target(listener,clip));
        }
        if(listener instanceof ContainerEventHandler container)
            for(var child:container.children())walk(child,clip,result,seen,depth+1);
    }
    private static List<Target> collect(Screen screen) {
        var list=new ArrayList<Target>();
        var seen=Collections.newSetFromMap(new IdentityHashMap<GuiEventListener,Boolean>());
        for(var child:screen.children())walk(child,new ScreenRectangle(0,0,screen.width,screen.height),list,seen,0);
        return list;
    }
    public JsonObject snapshot(Minecraft mc) {
        sampled=mc.gui.screen();targets=List.of();
        if(serial==Integer.MAX_VALUE)serial=0;serial++;
        var out=new JsonObject();out.addProperty("screen_open",sampled!=null);
        if(sampled==null){out.addProperty("text","No menu screen is open.");return out;}
        width=sampled.width;height=sampled.height;
        out.addProperty("overlay_active",mc.gui.overlay()!=null);
        out.addProperty("screen_id",serial);out.addProperty("title",bounded(sampled.getTitle().getString()));
        out.addProperty("type",sampled.getClass().getSimpleName());out.addProperty("width",width);out.addProperty("height",height);
        out.addProperty("chat_control_supported",false);
        targets=collect(sampled);var widgets=new JsonArray();
        var narrative=new StringBuilder("Menu: ").append(out.get("title").getAsString())
            .append(" (").append(width).append(" × ").append(height).append(" GUI units).\n");
        for(int index=0;index<targets.size();index++) {
            var target=targets.get(index);var component=target.listener();var rect=target.bounds();
            // Report only rectangles intersecting this screen; native routing still owns clipping.
            if(rect.right()<=0 || rect.bottom()<=0 || rect.left()>=width || rect.top()>=height)continue;
            var row=new JsonObject();row.addProperty("widget_id",index);
            row.addProperty("type",component.getClass().getSimpleName());row.addProperty("focused",component.isFocused());
            row.addProperty("x",rect.left());row.addProperty("y",rect.top());
            row.addProperty("width",rect.width());row.addProperty("height",rect.height());
            String label=component.getClass().getSimpleName();boolean active=true;
            if(component instanceof AbstractWidget widget){label=widget.getMessage().getString();active=widget.active;}
            else if(component instanceof WorldSelectionList.Entry entry)label=entry.getNarration().getString();
            row.addProperty("label",bounded(label));row.addProperty("active",active);
            if(component instanceof EditBox box) {
                row.addProperty("editable",box.canConsumeInput());row.addProperty("character_count",box.getValue().length());
                // Never echo edit-box contents: modded login/password fields may contain credentials.
            }
            widgets.add(row);narrative.append("- [").append(index).append("] ").append(bounded(label))
                .append(active?"":" (disabled)").append(component instanceof EditBox?" [text field]":"").append("\n");
        }
        out.add("widgets",widgets);out.addProperty("text",narrative.toString());return out;
    }
    private Screen require(Minecraft mc,JsonObject q) {
        int id=Protocol.integer(q,"screen_id",1,Integer.MAX_VALUE);
        Screen screen=mc.gui.screen();
        if(sampled==null || screen!=sampled || id!=serial || screen.width!=width || screen.height!=height)
            throw new IllegalStateException("stale_screen");
        if(mc.gui.overlay()!=null)throw new IllegalStateException("menu_overlay_active");
        if(screen instanceof ChatScreen)throw new IllegalStateException("chat_control_not_supported");
        return screen;
    }
    private static int modifiers(JsonObject q) {
        if(!q.has("modifiers"))return 0;
        if(!q.get("modifiers").isJsonArray() || q.getAsJsonArray("modifiers").size()>2)
            throw new IllegalArgumentException("invalid_modifiers");
        int result=0;
        for(var value:q.getAsJsonArray("modifiers")){
            if(!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString())throw new IllegalArgumentException("invalid_modifiers");
            int flag=switch(value.getAsString()){case "shift"->InputConstants.MOD_SHIFT;case "control"->InputConstants.MOD_CONTROL;default->throw new IllegalArgumentException("invalid_modifier");};
            if((result&flag)!=0)throw new IllegalArgumentException("duplicate_modifier");result|=flag;
        }
        return result;
    }
    public JsonObject act(Minecraft mc,JsonObject q) {
        String op=Protocol.operation(q);
        switch(op) {
            case "menu_click" -> {
                Protocol.fields(q,"screen_id","widget_id","x","y","button");Screen screen=require(mc,q);
                int button=q.has("button")?Protocol.integer(q,"button",0,1):0;double x,y;
                if(q.has("widget_id")) {
                    if(q.has("x") || q.has("y"))throw new IllegalArgumentException("widget_or_coordinates_not_both");
                    int id=Protocol.integer(q,"widget_id",0,Math.max(0,targets.size()-1));
                    if(id>=targets.size())throw new IllegalArgumentException("invalid_widget");
                    Target target=targets.get(id);
                    boolean found=collect(screen).stream().anyMatch(t->t.listener()==target.listener() && t.bounds().equals(target.bounds()));
                    if(!found || target.listener() instanceof AbstractWidget widget && (!widget.active || !widget.visible))
                        throw new IllegalStateException("stale_or_disabled_widget");
                    var rect=target.bounds();x=Math.max(0,rect.left())+(Math.min(width,rect.right())-Math.max(0,rect.left()))/2.0;
                    y=Math.max(0,rect.top())+(Math.min(height,rect.bottom())-Math.max(0,rect.top()))/2.0;
                    if(x<0 || x>=width || y<0 || y>=height)throw new IllegalStateException("widget_off_screen");
                } else {x=Protocol.number(q,"x",0,width-1);y=Protocol.number(q,"y",0,height-1);}
                var event=new MouseButtonEvent(x,y,new MouseButtonInfo(MenuInput.mouseButton(button),0));
                screen.mouseMoved(x,y);screen.mouseClicked(event,false);screen.mouseReleased(event);screen.afterMouseAction();
            }
            case "menu_key" -> {
                Protocol.fields(q,"screen_id","key","modifiers");Screen screen=require(mc,q);
                Integer code=KEYS.get(Protocol.string(q,"key"));if(code==null)throw new IllegalArgumentException("unsupported_menu_key");
                int mods=modifiers(q);var event=MenuInput.key(code,mods);
                screen.keyPressed(event);screen.keyReleased(event);screen.afterKeyboardAction();
            }
            case "menu_text" -> {
                Protocol.fields(q,"screen_id","text","replace");Screen screen=require(mc,q);
                String text=Protocol.string(q,"text");
                if(text.length()>2048 || text.codePoints().anyMatch(c->Character.isISOControl(c) || c==0x2028 || c==0x2029))
                    throw new IllegalArgumentException("invalid_menu_text");
                boolean replace=false;
                if(q.has("replace")) {
                    var value=q.get("replace");
                    if(!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("expected_boolean: replace");
                    replace=value.getAsBoolean();
                }
                GuiEventListener focus=screen.getFocused();int depth=0;
                while(focus instanceof ContainerEventHandler container && depth++<16)focus=container.getFocused();
                if(!(focus instanceof EditBox box) || !box.canConsumeInput())throw new IllegalStateException("focus_editable_text_field_first");
                if(replace) {
                    screen.keyPressed(MenuInput.selectAll());
                    screen.keyReleased(MenuInput.selectAll());
                    screen.keyPressed(MenuInput.key(InputConstants.KEY_BACKSPACE,0));
                    screen.keyReleased(MenuInput.key(InputConstants.KEY_BACKSPACE,0));
                }
                text.codePoints().forEach(c->screen.charTyped(new CharacterEvent(c)));
                screen.afterKeyboardAction();
            }
            case "menu_scroll" -> {
                Protocol.fields(q,"screen_id","x","y","amount");Screen screen=require(mc,q);
                double x=Protocol.number(q,"x",0,width-1),y=Protocol.number(q,"y",0,height-1);
                double amount=Protocol.number(q,"amount",-20,20);
                screen.mouseMoved(x,y);screen.mouseScrolled(x,y,0,amount);screen.afterMouseAction();
            }
            default -> throw new IllegalArgumentException("unknown_menu_operation");
        }
        // One-use snapshot: every accepted UI action requires a refreshed description.
        sampled=null;targets=List.of();
        return Protocol.ok("Native menu event submitted. Call menu again before the next event.");
    }
}
