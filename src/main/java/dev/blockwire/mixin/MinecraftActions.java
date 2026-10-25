package dev.blockwire.mixin;

import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

/** Accessor interfaces are added to the target class by Mixin. */
@Mixin(Minecraft.class)
public interface MinecraftActions {
    @Invoker("startAttack") boolean blockwire$attack();
    @Invoker("startUseItem") void blockwire$use();
}
