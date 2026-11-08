package dev.blockwire.mixin;

import net.minecraft.client.gui.screens.inventory.CreativeModeInventoryScreen;
import net.minecraft.world.item.CreativeModeTab;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.inventory.Slot;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

/** Only vanilla catalog/tab and native slot actions; no stack field access. */
@Mixin(CreativeModeInventoryScreen.class)
public interface CreativeInventoryAccess {
    @Invoker("selectTab") void blockwire$selectTab(CreativeModeTab tab);
    @Invoker("slotClicked") void blockwire$slotClicked(Slot slot,int index,int button,ContainerInput mode);
}
