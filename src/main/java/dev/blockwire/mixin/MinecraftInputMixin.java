package dev.blockwire.mixin;

import dev.blockwire.Blockwire;
import com.mojang.blaze3d.platform.InputConstants;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;

/** Native attack/use only; no custom packets, damage, reach, inventory or movement engine. */
@Mixin(Minecraft.class)
public abstract class MinecraftInputMixin {
    @Inject(method="handleGlobalKeyPress",at=@At("HEAD"),cancellable=true)
    private void blockwire$toggle(InputConstants.Key key,boolean control,CallbackInfoReturnable<Boolean> ci) {
        if(Blockwire.toggleKey(key))ci.setReturnValue(true);
    }
    // Background local automation must not depend on the desktop mouse being grabbed.
    @ModifyVariable(method="continueAttack",at=@At("HEAD"),argsOnly=true)
    private boolean blockwire$heldAttack(boolean original) {
        return original || Blockwire.holdingAttack();
    }
}
