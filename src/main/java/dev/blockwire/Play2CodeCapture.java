package dev.blockwire;

import com.google.gson.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.PosixFilePermissions;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;

/** Private append-only raw capture. It records observations only and never owns an input. */
final class Play2CodeCapture implements AutoCloseable {
    static final String EVENT_SCHEMA="blockwire.play2code.event.v1";
    static final String CAPTURE_SCHEMA="blockwire.play2code.capture.v1";
    static final long MAX_EVENTS=300_000;
    static final long MAX_BYTES=256L*1024*1024;
    static final int MAX_EVENT_BYTES=128*1024;
    private static final Set<String> RESERVED=Set.of("schema","recording_id","sequence","type","wall_time_ms","monotonic_ns");
    private static final DateTimeFormatter ID_TIME=DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss.SSS'Z'").withZone(ZoneOffset.UTC);
    private static final Gson PRETTY=new GsonBuilder().setPrettyPrinting().create();

    private final String id;
    private final Path directory,partial,timeline;
    private BufferedWriter writer;
    private long sequence,bytes;
    private final long startedMs=System.currentTimeMillis(),startedNs=System.nanoTime();
    private boolean finished;

    private Play2CodeCapture(Path root,String id) throws IOException {
        this.id=id;
        if(Files.isSymbolicLink(root))throw new IOException("symlink_recording_root");
        Files.createDirectories(root);privateDirectory(root);
        if(!Files.isDirectory(root,LinkOption.NOFOLLOW_LINKS))throw new IOException("invalid_recording_root");
        directory=root.resolve(id);
        if(Files.exists(directory,LinkOption.NOFOLLOW_LINKS))throw new IOException("recording_id_exists");
        Files.createDirectory(directory);privateDirectory(directory);
        partial=directory.resolve(".raw-timeline.jsonl.partial");timeline=directory.resolve("raw-timeline.jsonl");
        writer=Files.newBufferedWriter(partial,StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE);
        privateFile(partial);
    }
    static Play2CodeCapture start(Path root,JsonObject start) throws IOException {
        var capture=new Play2CodeCapture(root,newId());
        try {capture.append("recording_start",start);return capture;}
        catch(IOException|RuntimeException error){try{capture.close();}catch(IOException ignored){}throw error;}
    }
    private static String newId() {
        return ID_TIME.format(Instant.now())+"-"+UUID.randomUUID().toString().substring(0,8);
    }
    String id(){return id;}
    Path directory(){return directory;}
    long eventCount(){return sequence;}
    long startedMs(){return startedMs;}
    long startedNs(){return startedNs;}

    synchronized long append(String type,JsonObject details) throws IOException {
        if(finished || writer==null)throw new IOException("capture_closed");
        if(type==null || !type.matches("[a-z][a-z0-9_]{0,63}"))throw new IllegalArgumentException("invalid_event_type");
        if(sequence>=MAX_EVENTS)throw new IOException("recording_event_limit");
        var event=new JsonObject();event.addProperty("schema",EVENT_SCHEMA);event.addProperty("recording_id",id);
        event.addProperty("sequence",sequence);event.addProperty("type",type);
        event.addProperty("wall_time_ms",System.currentTimeMillis());event.addProperty("monotonic_ns",System.nanoTime());
        for(var entry:details.entrySet()) {
            if(RESERVED.contains(entry.getKey()))throw new IllegalArgumentException("reserved_event_field");
            event.add(entry.getKey(),entry.getValue().deepCopy());
        }
        String line=event.toString()+"\n";long size=line.getBytes(StandardCharsets.UTF_8).length;
        if(size>MAX_EVENT_BYTES)throw new IOException("recording_event_size_limit");
        if(bytes+size>MAX_BYTES)throw new IOException("recording_byte_limit");
        writer.write(line);bytes+=size;long written=sequence++;
        if(!type.equals("tick") || sequence%20==0)writer.flush();
        return written;
    }
    synchronized void finish(String status,String reason,JsonObject stop,JsonObject metadata) throws IOException {
        if(finished)return;
        IOException failure=null;
        try {append("recording_stop",stop);writer.flush();}
        catch(IOException error){failure=error;status="failed";reason="timeline_write_failed";}
        finally {try{writer.close();}catch(IOException error){if(failure==null)failure=error;}writer=null;finished=true;}
        boolean sealed=false;
        if(failure==null) {
            try {Files.move(partial,timeline,StandardCopyOption.ATOMIC_MOVE);}
            catch(AtomicMoveNotSupportedException unsupported){Files.move(partial,timeline);}
            privateFile(timeline);sealed=true;
        }
        var out=new JsonObject();out.addProperty("schema",CAPTURE_SCHEMA);out.addProperty("recording_id",id);
        out.addProperty("status",status);out.addProperty("reason",reason);out.addProperty("timeline",sealed?timeline.getFileName().toString():partial.getFileName().toString());
        out.addProperty("timeline_sealed",sealed);out.addProperty("event_count",sequence);out.addProperty("timeline_bytes",bytes);
        out.addProperty("started_at_ms",startedMs);out.addProperty("ended_at_ms",System.currentTimeMillis());
        out.addProperty("duration_ns",Math.max(0,System.nanoTime()-startedNs));
        for(var entry:metadata.entrySet())out.add(entry.getKey(),entry.getValue().deepCopy());
        writeJson(directory.resolve("capture.json"),out);
        if(failure!=null)throw failure;
    }
    public synchronized void close() throws IOException {
        if(writer!=null){writer.close();writer=null;}finished=true;
    }
    private static void writeJson(Path path,JsonObject value) throws IOException {
        Path temporary=path.resolveSibling("."+path.getFileName()+"."+UUID.randomUUID()+".partial");
        Files.writeString(temporary,PRETTY.toJson(value)+"\n",StandardCharsets.UTF_8,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE);
        privateFile(temporary);
        try {Files.move(temporary,path,StandardCopyOption.ATOMIC_MOVE);}
        catch(AtomicMoveNotSupportedException unsupported){Files.move(temporary,path);}
        privateFile(path);
    }
    private static void privateDirectory(Path path) throws IOException {
        try {Files.setPosixFilePermissions(path,PosixFilePermissions.fromString("rwx------"));}
        catch(UnsupportedOperationException ignored) {}
    }
    private static void privateFile(Path path) throws IOException {
        try {Files.setPosixFilePermissions(path,PosixFilePermissions.fromString("rw-------"));}
        catch(UnsupportedOperationException ignored) {}
    }
}
