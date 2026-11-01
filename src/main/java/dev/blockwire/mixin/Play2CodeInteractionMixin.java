package dev.blockwire.mixin;

import dev.blockwire.Blockwire;
import net.minecraft.client.multiplayer.MultiPlayerGameMode;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.phys.BlockHitResult;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** Read-only correlation hooks around native human mining/use dispatch. */
@Mixin(MultiPlayerGameMode.class)
public abstract class Play2CodeInteractionMixin {
    @Inject(method="startDestroyBlock",at=@At("HEAD"))
    private void blockwire$recordDestroy(BlockPos position,Direction face,CallbackInfoReturnable<Boolean> ci) {
        Blockwire.recordBreakIntent(position,face);
    }
    @Inject(method="useItemOn",at=@At("HEAD"))
    private void blockwire$recordUse(LocalPlayer player,InteractionHand hand,BlockHitResult hit,
                                     CallbackInfoReturnable<InteractionResult> ci) {
        Blockwire.recordUseIntent(player,hand,hit);
    }
}
