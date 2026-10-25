package dev.blockwire;

import com.google.gson.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.enchantment.ItemEnchantments;
import net.minecraft.world.phys.*;
import java.util.*;

/** Bounded, client-known snapshots, never arbitrary NBT or a server-world scan. */
public final class Observations {
    private Observations() {}
    private static String text(String s) {return s.length()>240?s.substring(0,240):s;}
    public static JsonObject item(ItemStack stack) {
        var o=new JsonObject();
        o.addProperty("empty",stack.isEmpty());
        if(stack.isEmpty())return o;
        o.addProperty("item",BuiltInRegistries.ITEM.getKey(stack.getItem()).toString());
        o.addProperty("name",text(stack.getHoverName().getString()));
        o.addProperty("count",stack.getCount());
        if(stack.isDamageableItem()){o.addProperty("damage",stack.getDamageValue());o.addProperty("max_damage",stack.getMaxDamage());}
        var ench=new JsonArray();
        for(var type:List.of(DataComponents.ENCHANTMENTS,DataComponents.STORED_ENCHANTMENTS)) {
            for(var entry:stack.getOrDefault(type,ItemEnchantments.EMPTY).entrySet()) {
                var e=new JsonObject();
                e.addProperty("id",entry.getKey().unwrapKey().map(k->k.identifier().toString()).orElse("unknown"));
                e.addProperty("level",entry.getIntValue());ench.add(e);
            }
        }
        o.add("enchantments",ench);return o;
    }
    public static JsonObject inventory(Minecraft mc) {
        var p=mc.player;var out=new JsonObject();var items=new JsonArray();
        for(int index=0;index<p.getInventory().getContainerSize();index++) {
            var stack=p.getInventory().getItem(index);if(stack.isEmpty())continue;
            var row=item(stack);row.addProperty("inventory_index",index);items.add(row);
        }
        out.add("items",items);out.addProperty("selected_hotbar",p.getInventory().getSelectedSlot());
        out.add("carried",item(p.containerMenu.getCarried()));
        boolean open=mc.gui.screen() instanceof AbstractContainerScreen<?>;
        out.addProperty("container_open",open);
        if(open) {
            var menu=p.containerMenu;out.addProperty("menu_id",menu.containerId);out.addProperty("state_id",menu.getStateId());
            var slots=new JsonArray();
            for(var slot:menu.slots) {
                var row=item(slot.getItem());row.addProperty("slot",slot.index);row.addProperty("active",slot.isActive());
                row.addProperty("x",slot.x);row.addProperty("y",slot.y);slots.add(row);
            }
            out.add("slots",slots);
        }
        StringBuilder narrative=new StringBuilder("Inventory (player indices are NOT menu slot IDs):\n");
        for(var el:items) {
            var row=el.getAsJsonObject();narrative.append("- [").append(row.get("inventory_index").getAsInt()).append("] ")
                .append(row.get("count").getAsInt()).append(" × ").append(row.get("name").getAsString())
                .append(" (").append(row.get("item").getAsString()).append(")\n");
        }
        if(items.isEmpty())narrative.append("Empty.\n");
        narrative.append(open?"Container open. Use slots + current menu_id/state_id for clicks.":"No container screen open.");
        out.addProperty("text",narrative.toString());return out;
    }
    public static JsonObject scene(Minecraft mc) {
        var out=new JsonObject();out.addProperty("protocol",1);out.addProperty("sampled_at_ms",System.currentTimeMillis());
        if(mc.gui.screen()!=null)out.addProperty("screen",text(mc.gui.screen().getTitle().getString()));
        if(mc.player==null || mc.level==null) {out.addProperty("in_world",false);out.addProperty("text","Not in a world.");return out;}
        var p=mc.player;out.addProperty("in_world",true);out.addProperty("alive",p.isAlive());
        out.addProperty("dimension",mc.level.dimension().identifier().toString());
        var pos=new JsonArray();pos.add(p.getX());pos.add(p.getY());pos.add(p.getZ());out.add("position",pos);
        var eye=new JsonArray();eye.add(p.getEyePosition().x);eye.add(p.getEyePosition().y);eye.add(p.getEyePosition().z);out.add("eye_position",eye);
        out.addProperty("yaw",p.getYRot());out.addProperty("pitch",p.getXRot());out.addProperty("health",p.getHealth());
        out.addProperty("max_health",p.getMaxHealth());out.addProperty("hunger",p.getFoodData().getFoodLevel());
        out.addProperty("on_ground",p.onGround());out.add("holding",item(p.getMainHandItem()));
        out.addProperty("biome",mc.level.getBiome(p.blockPosition()).unwrapKey().map(k->k.identifier().toString()).orElse("unknown"));
        String target="nothing in reach";
        if(mc.hitResult instanceof BlockHitResult block && mc.hitResult.getType()==HitResult.Type.BLOCK) {
            var b=mc.level.getBlockState(block.getBlockPos());var t=new JsonObject();
            t.addProperty("kind","block");t.addProperty("id",BuiltInRegistries.BLOCK.getKey(b.getBlock()).toString());
            var xyz=new JsonArray();xyz.add(block.getBlockPos().getX());xyz.add(block.getBlockPos().getY());xyz.add(block.getBlockPos().getZ());
            t.add("position",xyz);t.addProperty("face",block.getDirection().getName());out.add("target",t);
            target=t.get("id").getAsString()+" at "+xyz;
        } else if(mc.hitResult instanceof EntityHitResult hit) {
            var t=entity(hit.getEntity(),p);t.addProperty("kind","entity");out.add("target",t);target=t.get("name").getAsString();
        }
        var visible=new JsonArray();
        // Approximation, not a claim about final pixel visibility or all nearby entities.
        for(Entity entity:mc.level.entitiesForRendering()) {
            if(entity==p || entity.isInvisibleTo(p) || p.distanceToSqr(entity)>24*24)continue;
            var delta=entity.getEyePosition().subtract(p.getEyePosition());
            if(delta.lengthSqr()>0 && delta.normalize().dot(p.getViewVector(1))>.5 && p.hasLineOfSight(entity)) {
                visible.add(entity(entity,p));if(visible.size()==16)break;
            }
        }
        out.add("potentially_visible_entities",visible);
        out.addProperty("text",String.format(Locale.ROOT,
            "You are %s in %s (%s), at %.2f, %.2f, %.2f. Health %.1f/%.1f, hunger %d/20. Looking at %s. Holding %s. %d potentially visible entities.",
            p.isAlive()?"alive":"dead",out.get("dimension").getAsString(),out.get("biome").getAsString(),
            p.getX(),p.getY(),p.getZ(),p.getHealth(),p.getMaxHealth(),p.getFoodData().getFoodLevel(),target,
            p.getMainHandItem().isEmpty()?"nothing":text(p.getMainHandItem().getHoverName().getString()),visible.size()));
        return out;
    }
    private static JsonObject entity(Entity entity,Entity viewer) {
        var o=new JsonObject();o.addProperty("id",entity.getId());
        o.addProperty("type",BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString());
        o.addProperty("name",text(entity.getDisplayName().getString()));o.addProperty("distance",viewer.distanceTo(entity));return o;
    }
}
