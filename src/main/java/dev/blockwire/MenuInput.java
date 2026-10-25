package dev.blockwire;

import com.mojang.blaze3d.platform.InputConstants;
import net.minecraft.client.input.*;

/** Protocol buttons are zero-based; Minecraft 26.3 native screen input uses SDL numbering. */
public final class MenuInput {
    private MenuInput() {}
    public static int mouseButton(int button) {
        return switch(button) {
            case 0 -> InputConstants.MOUSE_BUTTON_LEFT;
            case 1 -> InputConstants.MOUSE_BUTTON_RIGHT;
            default -> throw new IllegalArgumentException("invalid_mouse_button");
        };
    }
    public static KeyEvent key(int scancode,int modifiers) {
        int logical=switch(scancode) {
            case InputConstants.KEY_A -> 'a';
            case InputConstants.KEY_RETURN -> 13;
            case InputConstants.KEY_ESCAPE -> 27;
            case InputConstants.KEY_TAB -> 9;
            case InputConstants.KEY_BACKSPACE -> 8;
            case InputConstants.KEY_DELETE -> 127;
            case InputConstants.KEY_SPACE -> 32;
            default -> scancode | (1<<30); // SDL_SCANCODE_MASK for non-character navigation keys.
        };
        return new KeyEvent(scancode,logical,modifiers);
    }
    public static KeyEvent selectAll() {
        return key(InputConstants.KEY_A,InputQuirks.EDIT_SHORTCUT_KEY_MODIFIER);
    }
}
