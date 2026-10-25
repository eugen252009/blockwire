package dev.blockwire;

import net.minecraft.client.KeyMapping;

/** Hold semantics remain bounded even when a vanilla mapping is configured as Toggle. */
public final class InputState {
    private InputState() {}
    public static void set(KeyMapping key,boolean down) {
        if(key.isDown()==down)return;
        key.setDown(down);
        // Vanilla ToggleKeyMapping ignores key-up. A second native press toggles it off.
        if(!down && key.isDown())key.setDown(true);
    }
}
