package dev.blockwire;

import com.google.gson.*;
import io.netty.bootstrap.ServerBootstrap;
import io.netty.channel.*;
import io.netty.channel.nio.NioEventLoopGroup;
import io.netty.channel.socket.SocketChannel;
import io.netty.channel.socket.nio.NioServerSocketChannel;
import io.netty.handler.codec.http.*;
import io.netty.handler.codec.http.websocketx.*;
import io.netty.handler.timeout.ReadTimeoutHandler;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.concurrent.Executor;
import java.util.concurrent.atomic.*;
import java.util.function.Function;

/** Transport knows no Minecraft state. All dispatch and release run on the supplied game executor. */
public final class BridgeServer implements AutoCloseable {
    private static final org.slf4j.Logger LOG=org.slf4j.LoggerFactory.getLogger("blockwire");
    private final EventLoopGroup accept = new NioEventLoopGroup(1), workers = new NioEventLoopGroup(1);
    private final AtomicReference<Channel> owner = new AtomicReference<>();
    private final AtomicInteger pending = new AtomicInteger(), peers = new AtomicInteger();
    private final Executor game;
    private final Function<JsonObject,JsonObject> dispatch;
    private final Runnable release;
    private final String token;
    private Channel listener;
    private volatile boolean closed;

    public BridgeServer(int port,String token,io.netty.handler.ssl.SslContext tls,Executor game,Function<JsonObject,JsonObject> dispatch,Runnable release) throws InterruptedException {
        this("127.0.0.1",port,token,tls,game,dispatch,release);
    }
    public BridgeServer(String host,int port,String token,io.netty.handler.ssl.SslContext tls,Executor game,Function<JsonObject,JsonObject> dispatch,Runnable release) throws InterruptedException {
        java.util.Objects.requireNonNull(tls,"TLS is required");
        if(!io.netty.util.NetUtil.isValidIpV4Address(host) && !io.netty.util.NetUtil.isValidIpV6Address(host))
            throw new IllegalArgumentException("host_must_be_literal_ip");
        this.token=token; this.game=game; this.dispatch=dispatch; this.release=release;
        try {
            listener=new ServerBootstrap().group(accept,workers).channel(NioServerSocketChannel.class)
                .childOption(ChannelOption.TCP_NODELAY,true)
                .childHandler(new ChannelInitializer<SocketChannel>() {
                    protected void initChannel(SocketChannel channel) {
                        if(peers.incrementAndGet()>8){peers.decrementAndGet();channel.close();return;}
                        channel.pipeline().addLast(new ChannelInboundHandlerAdapter(){
                            public void channelInactive(ChannelHandlerContext ctx) throws Exception {
                                peers.decrementAndGet();super.channelInactive(ctx);
                            }
                        });
                        var encryption=tls.newHandler(channel.alloc());
                        encryption.setHandshakeTimeoutMillis(5000);
                        channel.pipeline().addLast(encryption,new ReadTimeoutHandler(30),new HttpServerCodec(),
                            new HttpObjectAggregator(8192),new Handler());
                    }
                }).bind(new InetSocketAddress(host,port)).sync().channel();
        } catch (InterruptedException | RuntimeException e) { close(); throw e; }
    }
    public int port() { return ((InetSocketAddress)listener.localAddress()).getPort(); }
    private String authority() {
        String ip=((InetSocketAddress)listener.localAddress()).getAddress().getHostAddress();
        return (ip.contains(":")?"["+ip+"]":ip)+":"+port();
    }
    public boolean connected() { Channel c=owner.get(); return c!=null && c.isActive(); }

    private final class Handler extends SimpleChannelInboundHandler<Object> {
        private WebSocketServerHandshaker handshaker;
        protected void channelRead0(ChannelHandlerContext ctx,Object msg) {
            if (msg instanceof FullHttpRequest req) {
                String bearer=req.headers().get(HttpHeaderNames.AUTHORIZATION,"");
                boolean authorized=MessageDigest.isEqual(("Bearer "+token).getBytes(StandardCharsets.UTF_8),
                    bearer.getBytes(StandardCharsets.UTF_8));
                if (closed || !authorized || req.headers().contains(HttpHeaderNames.ORIGIN) ||
                    !req.method().equals(HttpMethod.GET) || !req.uri().equals("/v1")) {
                    reject(ctx,HttpResponseStatus.FORBIDDEN); return;
                }
                handshaker=new WebSocketServerHandshakerFactory("wss://"+authority()+"/v1",null,false,8192).newHandshaker(req);
                if (handshaker==null) { reject(ctx,HttpResponseStatus.BAD_REQUEST); return; }
                if (!owner.compareAndSet(null,ctx.channel())) { reject(ctx,HttpResponseStatus.CONFLICT); return; }
                handshaker.handshake(ctx.channel(),req).addListener(f->{ if(!f.isSuccess())ctx.close(); });
            } else if (msg instanceof PingWebSocketFrame ping) {
                ctx.writeAndFlush(new PongWebSocketFrame(ping.content().retain()));
            } else if (msg instanceof CloseWebSocketFrame) {
                ctx.close();
            } else if (msg instanceof TextWebSocketFrame frame && owner.get()==ctx.channel()) {
                if (pending.incrementAndGet()>32) { pending.decrementAndGet();ctx.close();return; }
                final JsonObject request;
                try {
                    request=JsonParser.parseString(frame.text()).getAsJsonObject();
                    JsonElement id=request.get("id");
                    if(id==null || !id.isJsonPrimitive() || id.getAsJsonPrimitive().isBoolean() || id.getAsString().length()>80)
                        throw new IllegalArgumentException("invalid_id");
                }
                catch (RuntimeException e) { pending.decrementAndGet();ctx.close();return; }
                long received=System.nanoTime();
                game.execute(()->{
                    try {
                        if (closed || owner.get()!=ctx.channel() || !ctx.channel().isActive()) return;
                        JsonObject reply=new JsonObject();
                        JsonElement id=request.get("id");
                        if (id!=null && id.isJsonPrimitive() && id.getAsString().length()<=80) reply.add("id",id);
                        try {
                            if(System.nanoTime()-received>2_000_000_000L)throw new IllegalStateException("expired_request");
                            reply.add("result",dispatch.apply(request));reply.addProperty("ok",true);
                        }
                        catch (IllegalArgumentException | IllegalStateException e) {
                            reply.addProperty("ok",false);reply.addProperty("error",e.getMessage());
                        } catch (RuntimeException e) {
                            release.run();
                            LOG.error("Blockwire action failed; held inputs released",e);
                            reply.addProperty("ok",false);reply.addProperty("error","internal_error");
                        }
                        ctx.writeAndFlush(new TextWebSocketFrame(reply.toString()));
                    } finally { pending.decrementAndGet(); }
                });
            } else ctx.close();
        }
        private void reject(ChannelHandlerContext ctx,HttpResponseStatus status) {
            ctx.writeAndFlush(new DefaultFullHttpResponse(HttpVersion.HTTP_1_1,status)).addListener(ChannelFutureListener.CLOSE);
        }
        public void channelInactive(ChannelHandlerContext ctx) {
            // Keep the lease occupied until its inputs are released on the game thread.
            game.execute(()->{if(owner.compareAndSet(ctx.channel(),null))release.run();});
        }
        public void exceptionCaught(ChannelHandlerContext ctx,Throwable cause) { ctx.close(); }
    }
    public void close() {
        closed=true;
        if(listener!=null)listener.close();
        Channel c=owner.get();if(c!=null)c.close();
        accept.shutdownGracefully();workers.shutdownGracefully();
    }
}
