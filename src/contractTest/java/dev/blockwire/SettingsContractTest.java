package dev.blockwire;

import com.google.gson.*;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Arrays;

/** MM01-MM08: optional linkage, GUI model effects and private preference persistence. No graphical client. */
public final class SettingsContractTest {
    private static int checks;
    private static void check(boolean value,String label) {if(!value)throw new AssertionError(label);checks++;}
    private static final class Backend implements LocalSettingsModel.Backend {
        boolean available=true,running,autoStart,failSave,failToggle;
        int toggles,saves;
        public LocalSettingsModel.Status status() {return new LocalSettingsModel.Status(available,running,false,autoStart,"127.0.0.1",8765);}
        public void toggleRuntime() {toggles++;if(!failToggle)running=!running;}
        public boolean saveStartup(boolean enabled) {saves++;if(failSave)return false;autoStart=enabled;return true;}
    }
    public static void main(String[] args) throws Exception {
        // MM01: the normal runtime deliberately has no Mod Menu classes, yet normal classes link.
        try {Class.forName("com.terraformersmc.modmenu.api.ModMenuApi");throw new AssertionError("MM01_modmenu_must_be_optional");}
        catch(ClassNotFoundException expected){checks++;}
        Class.forName("dev.blockwire.Blockwire",false,SettingsContractTest.class.getClassLoader());
        Class.forName("dev.blockwire.BlockwireSettingsScreen",false,SettingsContractTest.class.getClassLoader());checks++;
        var unavailable=Blockwire.localSettings();
        check(!unavailable.status().available() && !unavailable.saveStartup(true),"MM02_initialization_failure_cannot_enable");
        unavailable.toggleRuntime();check(!unavailable.status().running(),"MM02_no_runtime_without_private_tls");
        // MM03: opening/rebuilding/closing a model never saves or enables; drafts require explicit save.
        var backend=new Backend();var model=new LocalSettingsModel(backend);model.refresh();
        check(backend.toggles==0 && backend.saves==0 && !backend.running,"MM03_open_is_read_only");
        model.toggleStartupDraft();model.refresh();
        check(model.dirty() && model.draftAutoStart() && backend.saves==0,"MM03_draft_does_not_persist");
        check(!new LocalSettingsModel(backend).draftAutoStart(),"MM03_closing_discards_draft");
        check(model.save() && backend.autoStart && !backend.running,"MM04_save_does_not_enable_runtime");
        check(backend.saves==1 && !model.dirty(),"MM04_save_reflected_in_status");
        check(model.save() && backend.saves==1,"MM04_clean_save_has_no_write");
        check(model.toggleRuntime() && backend.running && backend.autoStart,"MM05_runtime_toggle_separate_from_startup");
        check(model.toggleRuntime() && !backend.running && backend.saves==1,"MM05_disable_has_no_config_write");
        backend.failToggle=true;check(!model.toggleRuntime(),"MM05_failed_bind_not_reported_enabled");
        model.toggleStartupDraft();backend.failSave=true;
        check(!model.save() && model.dirty() && backend.autoStart,"MM04_failed_save_keeps_draft");
        backend.available=false;model.refresh();int toggles=backend.toggles,saves=backend.saves;
        check(!model.toggleRuntime() && !model.save() && backend.toggles==toggles && backend.saves==saves,"MM02_unavailable_no_effects");
        check(Arrays.stream(LocalSettingsModel.Status.class.getRecordComponents()).noneMatch(c->c.getName().toLowerCase().contains("key")),"MM06_status_has_no_credential_field");

        Path root=Files.createTempDirectory("blockwire-settings-contract-");
        try {
            // MM07: selected legacy directory is retained; token and TLS bytes are never touched by save.
            Path dir=root.resolve("block-bridge");var config=BridgeConfig.load(dir);var tls=TlsIdentity.load(dir);
            byte[] token=Files.readAllBytes(dir.resolve("token")),identity=Files.readAllBytes(dir.resolve("tls/identity.p12")),
                certificate=Files.readAllBytes(dir.resolve("tls/certificate.pem"));
            var enabled=BridgeConfig.saveStartup(dir,config,true);
            check(enabled.enabled() && enabled.apiKey().equals(config.apiKey()) && enabled.serverIp().equals(config.serverIp()) &&
                enabled.port()==config.port(),"MM07_save_changes_only_startup_flag");
            check(BridgeConfig.parse(JsonParser.parseString(Files.readString(dir.resolve("settings.json"))).getAsJsonObject()).equals(enabled),"MM07_disk_matches_saved_status");
            check(Arrays.equals(token,Files.readAllBytes(dir.resolve("token"))) &&
                Arrays.equals(identity,Files.readAllBytes(dir.resolve("tls/identity.p12"))) &&
                Arrays.equals(certificate,Files.readAllBytes(dir.resolve("tls/certificate.pem"))),"MM07_token_and_tls_bytes_unchanged");
            check(!Files.exists(root.resolve("blockwire")),"MM07_legacy_directory_not_migrated");
            try(var paths=Files.list(dir)){check(paths.noneMatch(p->p.getFileName().toString().endsWith(".tmp")),"MM07_no_temporary_files_left");}
            if(FileSystems.getDefault().supportedFileAttributeViews().contains("posix"))
                check(Files.getPosixFilePermissions(dir.resolve("settings.json")).equals(PosixFilePermissions.fromString("rw-------")),"MM07_saved_config_private");
            byte[] before=Files.readAllBytes(dir.resolve("settings.json"));
            check(BridgeConfig.saveStartup(dir,enabled,true).equals(enabled) && Arrays.equals(before,Files.readAllBytes(dir.resolve("settings.json"))),"MM07_noop_preserves_exact_file_bytes");
            // MM08: stale/invalid/symlink/missing authority must never silently regenerate or overwrite it.
            try {BridgeConfig.saveStartup(dir,config,false);throw new AssertionError("MM08_stale_config_rejected");}
            catch(java.io.IOException expected){checks++;}
            check(Arrays.equals(before,Files.readAllBytes(dir.resolve("settings.json"))),"MM08_stale_rejection_without_write");
            Files.writeString(dir.resolve("settings.json"),"{}");
            try {BridgeConfig.saveStartup(dir,enabled,false);throw new AssertionError("MM08_invalid_config_rejected");}
            catch(IllegalArgumentException expected){checks++;}
            check(Files.readString(dir.resolve("settings.json")).equals("{}"),"MM08_invalid_not_migrated");
            Files.delete(dir.resolve("settings.json"));
            try {BridgeConfig.saveStartup(dir,enabled,false);throw new AssertionError("MM08_missing_config_rejected");}
            catch(java.io.IOException expected){checks++;}
            check(!Files.exists(dir.resolve("settings.json")),"MM08_missing_not_regenerated");
            if(FileSystems.getDefault().supportedFileAttributeViews().contains("posix")) {
                Path outside=root.resolve("outside.json");Files.write(outside,before);Files.createSymbolicLink(dir.resolve("settings.json"),outside);
                try {BridgeConfig.saveStartup(dir,enabled,false);throw new AssertionError("MM08_symlink_config_rejected");}
                catch(java.io.IOException expected){checks++;}
                check(Arrays.equals(before,Files.readAllBytes(outside)),"MM08_symlink_target_unchanged");
                Files.delete(dir.resolve("settings.json"));
                Path link=root.resolve("linked-directory");Files.createSymbolicLink(link,dir);
                try {BridgeConfig.saveStartup(link,enabled,false);throw new AssertionError("MM08_symlink_directory_rejected");}
                catch(java.io.IOException expected){checks++;}
            }
        } finally {TlsContractTest.deleteTree(root);}
        System.out.println("BLOCKWIRE_SETTINGS_CONTRACT_PASS checks="+checks);
    }
}
