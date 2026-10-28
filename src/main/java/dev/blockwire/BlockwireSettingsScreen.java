package dev.blockwire;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/** Ordinary local native GUI. No API keys, credential rotation or automatic Python activation. */
public final class BlockwireSettingsScreen extends Screen {
    private final Screen parent;
    private final LocalSettingsModel model;
    private Button runtime,startup,save;
    private Component feedback=Component.empty();
    private int top,left,contentWidth;

    public BlockwireSettingsScreen(Screen parent) {
        super(Component.translatable("blockwire.settings.title"));
        this.parent=parent;model=new LocalSettingsModel(Blockwire.localSettings());
    }
    protected void init() {
        model.refresh();
        contentWidth=Math.min(320,width-32);left=(width-contentWidth)/2;top=Math.max(8,(height-224)/2);
        runtime=addRenderableWidget(Button.builder(Component.empty(),button->{
            feedback=model.toggleRuntime()?Component.empty():Component.translatable("blockwire.settings.runtime_failed");
            updateButtons();
        }).bounds(left,top+68,contentWidth,20).tooltip(Tooltip.create(Component.translatable("blockwire.settings.runtime_hint"))).build());
        startup=addRenderableWidget(Button.builder(Component.empty(),button->{
            model.toggleStartupDraft();feedback=Component.empty();updateButtons();
        }).bounds(left,top+94,contentWidth,20).tooltip(Tooltip.create(Component.translatable("blockwire.settings.startup_hint"))).build());
        save=addRenderableWidget(Button.builder(Component.translatable("blockwire.settings.save"),button->{
            feedback=Component.translatable(model.save()?"blockwire.settings.saved":"blockwire.settings.save_failed");
            updateButtons();
        }).bounds(left,top+120,contentWidth,20).build());
        addRenderableWidget(Button.builder(Component.translatable("gui.done"),button->onClose())
            .bounds(left,height-28,contentWidth,20).build());
        updateButtons();
    }
    private void updateButtons() {
        var status=model.status();
        runtime.setMessage(Component.translatable(status.running()?"blockwire.settings.disable":"blockwire.settings.enable"));
        runtime.active=status.available();startup.active=status.available();
        startup.setMessage(Component.translatable("blockwire.settings.startup",
            Component.translatable(model.draftAutoStart()?"options.on":"options.off")));
        save.active=status.available() && model.dirty();
    }
    public void tick() {model.refresh();updateButtons();}
    public void onClose() {minecraft.gui.setScreen(parent);} // Discard unsaved startup draft; runtime changes are immediate.
    public void extractRenderState(GuiGraphicsExtractor graphics,int mouseX,int mouseY,float delta) {
        super.extractRenderState(graphics,mouseX,mouseY,delta);
        var status=model.status();
        graphics.centeredText(font,title,width/2,top,0xffffffff);
        String state=!status.available()?"unavailable":!status.running()?"disabled":status.connected()?"connected":"waiting";
        graphics.centeredText(font,Component.translatable("blockwire.settings.status."+state),width/2,top+20,
            status.available()?0xffffffff:0xffff8888);
        if(status.available()) {
            String host=status.bindAddress().contains(":")?"["+status.bindAddress()+"]":status.bindAddress();
            String address="wss://"+host+":"+status.port()+"/v1";
            graphics.centeredText(font,font.plainSubstrByWidth(address,contentWidth),width/2,top+34,0xffbbbbbb);
        }
        graphics.centeredText(font,Component.translatable("blockwire.settings.security"),width/2,top+48,0xffbbbbbb);
        graphics.centeredText(font,Component.translatable("blockwire.settings.file_hint"),width/2,top+151,0xffbbbbbb);
        graphics.centeredText(font,Component.translatable("blockwire.settings.stop_hint"),width/2,top+166,0xffbbbbbb);
        if(!feedback.getString().isEmpty())graphics.centeredText(font,
            font.plainSubstrByWidth(feedback.getString(),contentWidth),width/2,top+184,0xffffcc66);
    }
}
