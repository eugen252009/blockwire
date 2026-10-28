package dev.blockwire;

import com.google.gson.*;
import com.terraformersmc.modmenu.api.ModMenuApi;
import dev.blockwire.compat.BlockwireModMenu;

/** MM09: check actual optional API linkage/metadata without constructing a graphical Minecraft client. */
public final class ModMenuContractTest {
    public static void main(String[] args) throws Exception {
        try(var resource=ModMenuContractTest.class.getResourceAsStream("/fabric.mod.json")) {
            var metadata=JsonParser.parseString(new String(resource.readAllBytes(),java.nio.charset.StandardCharsets.UTF_8)).getAsJsonObject();
            if(metadata.getAsJsonObject("depends").has("modmenu"))throw new AssertionError("MM09_modmenu_must_not_be_required");
            if(!metadata.getAsJsonObject("entrypoints").getAsJsonArray("modmenu").get(0).getAsString().equals(BlockwireModMenu.class.getName()))
                throw new AssertionError("MM09_optional_entrypoint_registered");
            ModMenuApi api=new BlockwireModMenu();
            if(api.getModConfigScreenFactory()==null)throw new AssertionError("MM09_native_screen_factory_available");
            if(Blockwire.localSettings().status().available())throw new AssertionError("MM09_factory_does_not_initialize_or_enable_control");
        }
        System.out.println("BLOCKWIRE_MODMENU_API_CONTRACT_PASS checks=4");
    }
}
