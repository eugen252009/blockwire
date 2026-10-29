package dev.blockwire;

import java.util.*;

/** Independent, lower-only key leases. No planner; native ticks and monotonic time both bound each key. */
public final class InputLeases {
    private final Map<String,Integer> remaining=new HashMap<>();
    private final Map<String,Long> deadlines=new HashMap<>();
    public void reset(Map<String,Integer> ticks,long now) {
        clear();
        ticks.forEach((key,count)->{remaining.put(key,count);deadlines.put(key,now+count*50_000_000L);});
    }
    public Set<String> expire(long now) {
        var expired=new HashSet<String>();
        for(var entry:remaining.entrySet()) {
            int count=entry.getValue();entry.setValue(count-1);
            if(count<=0 || now>=deadlines.get(entry.getKey()))expired.add(entry.getKey());
        }
        for(String key:expired){remaining.remove(key);deadlines.remove(key);}
        return Set.copyOf(expired);
    }
    /** Omitted durations retain an existing lease, never restart it. Expired keys cannot be resurrected. */
    public Set<String> replace(Set<String> desired,Map<String,Integer> renew,long now) {
        remaining.keySet().removeIf(key->!desired.contains(key) || !active(key,now));
        deadlines.keySet().retainAll(remaining.keySet());
        renew.forEach((key,count)->{remaining.put(key,count);deadlines.put(key,now+count*50_000_000L);});
        return Set.copyOf(remaining.keySet());
    }
    public void cap(int ticks,long now) {
        remaining.replaceAll((key,count)->Math.min(count,ticks));
        deadlines.replaceAll((key,deadline)->Math.min(deadline,now+ticks*50_000_000L));
    }
    public boolean active(String key,long now) {return deadlines.containsKey(key) && now<deadlines.get(key);}
    public void clear(){remaining.clear();deadlines.clear();}
}
