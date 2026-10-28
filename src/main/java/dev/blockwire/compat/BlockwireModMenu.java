package dev.blockwire.compat;

import com.terraformersmc.modmenu.api.ConfigScreenFactory;
import com.terraformersmc.modmenu.api.ModMenuApi;
import dev.blockwire.BlockwireSettingsScreen;

/** Loaded only by Mod Menu's optional entrypoint, never by the normal client initializer. */
public final class BlockwireModMenu implements ModMenuApi {
    @Override
    public ConfigScreenFactory<BlockwireSettingsScreen> getModConfigScreenFactory() {
        return BlockwireSettingsScreen::new;
    }
}
