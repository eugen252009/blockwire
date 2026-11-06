"""Actual pinned TLS WebSocket + simulated native producer, NOT Minecraft acceptance."""
import json,ssl,subprocess,tempfile,threading,time,unittest
from pathlib import Path
from websockets.sync.server import serve
from blockwire import Bridge,BridgeError
class NativeStreamContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.cert=self.root/'certificate.pem';self.key=self.root/'key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256','-nodes','-keyout',str(self.key),'-out',str(self.cert),'-days','1','-subj','/CN=block-bridge.invalid','-addext','subjectAltName=DNS:block-bridge.invalid'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);self.key.chmod(0o600)
        self.calls=[];self.notify=threading.Event();self.frame_count=1;self.wrong_actor=False
        def handler(ws):
            if ws.request.headers.get('Authorization')!='Bearer '+'a'*64:ws.close();return
            for body in ws:
                q=json.loads(body);self.calls.append(q)
                if q['op']=='events_configure' and q.get('enabled'):
                    for n in range(1,self.frame_count+1):ws.send(json.dumps({'type':'native_event','name':'player.chat','actor_session':'wrong' if self.wrong_actor else 'actor','sequence':n,'data':{'message':str(n),'channel':'player_chat'}}))
                ws.send(json.dumps({'id':q['id'],'ok':True,'result':{'configured':True}}))
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(self.cert,self.key)
        # Isolate frame demultiplexing from a reproduced Python 3.11 threaded-SSL
        # post-handshake ticket stall (both peers wait before HTTP). TLS 1.3,
        # certificate/auth checks and the client's deadline remain unchanged;
        # production Netty TLS is covered independently by tests/tls_interop.py.
        ctx.num_tickets=0
        self.server=serve(handler,'127.0.0.1',0,ssl=ctx);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();port=self.server.socket.getsockname()[1];self.bridge=Bridge('a'*64,f'wss://127.0.0.1:{port}/v1',certificate=self.cert)
    def tearDown(self):self.bridge.close();self.server.shutdown();self.thread.join(5);self.tmp.cleanup()
    def test_NS01_event_before_config_ack_and_responses_demultiplexed(self):
        self.bridge.start_native_events('actor',self.notify.set);self.assertTrue(self.notify.wait(2));self.assertEqual(self.bridge.call('look',yaw=0,pitch=0),{'configured':True});self.assertEqual(self.bridge.drain_native_events()[0]['sequence'],1);self.assertEqual(len(self.calls),2)
    def test_NS02_bounded_event_queue_reports_loss_not_control_loss(self):
        self.frame_count=90;self.bridge.start_native_events('actor',self.notify.set);self.assertEqual(len(self.bridge.drain_native_events()),64);self.assertEqual(self.bridge.event_dropped,26);self.assertEqual(self.bridge.call('stop'),{'configured':True})
    def test_NS03_wrong_actor_terminal_no_reconnect(self):
        self.wrong_actor=True
        with self.assertRaises(BridgeError):self.bridge.start_native_events('actor',self.notify.set)
        old=len(self.calls)
        with self.assertRaises(BridgeError):self.bridge.call('look',yaw=0,pitch=0)
        self.assertEqual(len(self.calls),old)
if __name__=='__main__':unittest.main()
