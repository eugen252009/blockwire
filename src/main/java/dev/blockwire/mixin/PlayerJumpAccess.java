package dev.blockwire.mixin;

import net.minecraft.world.entity.player.Player;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** Read-only native double-tap timer; never alters abilities or flight state. */
@Mixin(Player.class)
public interface PlayerJumpAccess {
    @Accessor("jumpTriggerTime") int blockwire$jumpTriggerTime();
}
