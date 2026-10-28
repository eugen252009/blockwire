package dev.blockwire;

/** Local GUI state only: opening/refreshing/cancelling never enables control or saves a draft. */
public final class LocalSettingsModel {
    public record Status(boolean available,boolean running,boolean connected,boolean autoStart,String bindAddress,int port) {}
    public interface Backend {
        Status status();
        void toggleRuntime();
        boolean saveStartup(boolean enabled);
    }
    private final Backend backend;
    private Status status;
    private boolean draftAutoStart;
    public LocalSettingsModel(Backend backend) {
        this.backend=backend;status=backend.status();draftAutoStart=status.autoStart();
    }
    public Status status() {return status;}
    public void refresh() {status=backend.status();}
    public boolean draftAutoStart() {return draftAutoStart;}
    public boolean dirty() {return draftAutoStart!=status.autoStart();}
    public void toggleStartupDraft() {if(status.available())draftAutoStart=!draftAutoStart;}
    public boolean toggleRuntime() {
        refresh();
        if(!status.available())return false;
        boolean before=status.running();backend.toggleRuntime();refresh();return status.running()!=before;
    }
    public boolean save() {
        refresh();
        if(!status.available())return false;
        if(!dirty())return true;
        boolean saved=backend.saveStartup(draftAutoStart);refresh();
        return saved && status.autoStart()==draftAutoStart;
    }
}
