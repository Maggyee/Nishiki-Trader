"""Disposable fixed installation/UID gateway integration; never install on the host."""

from __future__ import annotations

import argparse
import base64
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

SCENARIOS = ("success", "code_drift", "account_drift", "storage_drift", "controller_crash")
TLS_SCENARIOS = (
    "tls_success",
    "tls_slow_body",
    "tls_bad_certificate",
    "tls_duplicate_weight",
    "tls_truncated",
    "tls_crash",
)
RECEIPT_SCENARIOS = TLS_SCENARIOS + (
    "receipt_child_death",
    "receipt_child_stopped",
    "receipt_controller_crash",
    "receipt_code_drift",
    "receipt_storage_drift",
)
NATIVE_SCENARIOS = (
    "tls_success",
    "tls_slow_body",
    "native_precision",
    "receipt_runtime_drift",
    "tls_bad_certificate",
    "receipt_child_stopped",
    "receipt_controller_crash",
)
IPC_SCENARIOS = (
    "ipc_success",
    "ipc_child_death",
    "ipc_code_drift",
    "ipc_account_drift",
    "ipc_storage_drift",
    "ipc_controller_crash",
)
REQUEST_SCENARIOS = IPC_SCENARIOS + ("ipc_runtime_drift",)
SEQUENCE_SCENARIOS = (
    "sequence_success",
    "sequence_metadata_mismatch",
    "sequence_balance_drift",
    "sequence_second_precision",
    "sequence_child_stopped",
    "sequence_controller_crash",
    "sequence_code_drift",
)
ORDER_SCENARIOS = (
    "orders_success",
    "orders_empty",
    "orders_changed",
    "orders_precision",
    "orders_duplicate",
    "orders_lock_mismatch",
    "orders_child_stopped",
    "orders_controller_crash",
    "orders_code_drift",
)
ROUTE_SCENARIOS = (
    "routes_success",
    "routes_two_hops",
    "routes_missing",
    "routes_depth",
    "routes_precision",
    "routes_duplicate",
    "routes_disabled",
    "routes_child_stopped",
    "routes_controller_crash",
    "routes_code_drift",
)
WS_SCENARIOS = (
    "routes_ws_success",
    "routes_ws_two_hops",
    "routes_ws_bad_certificate",
    "routes_ws_bad_upgrade",
    "routes_ws_peer_close",
    "routes_ws_stall",
    "routes_ws_code_drift",
    "routes_ws_controller_crash",
)
SIGNED_WS_SCENARIOS = (
    "routes_ws_success",
    "routes_ws_two_hops",
    "routes_ws_bad_response",
    "routes_ws_wrong_subscription",
    "routes_ws_precision",
    "routes_ws_extra_event",
    "routes_ws_child_stopped",
    "routes_ws_controller_crash",
    "routes_ws_code_drift",
)
MARKET_WS_SCENARIOS = (
    "routes_ws_success",
    "routes_ws_two_hops",
    "routes_ws_overlap",
    "routes_ws_gap",
    "routes_ws_duplicate_update",
    "routes_ws_wrong_stream",
    "routes_ws_market_precision",
    "routes_ws_missing_symbol",
    "routes_ws_extra_market",
    "routes_ws_child_stopped",
    "routes_ws_code_drift",
    "routes_ws_controller_crash",
)
SNAPSHOT_WS_SCENARIOS = (
    "snapshot_success",
    "snapshot_two_hops",
    "snapshot_gap",
    "snapshot_bad_http",
)
FIXTURE_BOOKS = [
    {"symbol": asset + "USDT", "bidPrice": price, "askPrice": ask, "bidQty": "10", "askQty": "10"}
    for asset, price, ask in (
        ("BTC", "60000", "60001"),
        ("ETH", "3000", "3001"),
        ("BNB", "250", "251"),
    )
]
FIXTURE_ORDERS = [
    {
        "symbol": symbol,
        "orderId": order_id,
        "clientOrderId": "fixture-" + str(order_id),
        "price": price,
        "origQty": qty,
        "executedQty": filled,
        "cummulativeQuoteQty": quote,
        "status": status,
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": side,
        "time": 1700000000000,
        "updateTime": 1700000001000,
        "isWorking": True,
        "icebergQty": "0",
        "stopPrice": "0",
        "orderListId": -1,
        "origQuoteOrderQty": "0",
    }
    for symbol, order_id, price, qty, filled, quote, status, side in (
        ("BTCUSDT", 101, "12500.00000000", "0.00100000", "0", "0", "NEW", "BUY"),
        (
            "BNBUSDT",
            102,
            "250.00000000",
            "0.20000000",
            "0.10000000",
            "25",
            "PARTIALLY_FILLED",
            "SELL",
        ),
        ("BTCUSDT", 103, "60000.00000000", "0.00100000", "0", "0", "NEW", "SELL"),
    )
]
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


def load(raw):
    scope = {"__name__": "installed_gateway_acceptance"}
    exec(compile(raw, "<fixed-fixture-source>", "exec"), scope)
    return scope


PROBE = r"""
import errno,json,os,socket
from pathlib import Path
checks=[]
def denied(name, operation):
    try:
        result=operation()
    except OSError as exc:
        if exc.errno not in (errno.EACCES,errno.EPERM,errno.EROFS): raise
        checks.append(name)
    else:
        if isinstance(result,int): os.close(result)
        raise RuntimeError('unexpected_permission:'+name)
runtime=Path('/run/trader-native-runtime')
if runtime.exists():
    denied('native_runtime_write',lambda:os.open(runtime/'bin/python3.12',os.O_WRONLY))
    denied('native_runtime_replace',lambda:os.unlink(runtime/'bin/python3.12'))
code=Path('/usr/local/lib/trader-egress')
for name in ('installed_gateway.py','gateway_tls.py','gateway_joint_ipc.py','gateway_tls_receipt.py','gateway_native_runtime.py','gateway_native_receipt.py','gateway_native_requests.py','gateway_native_account.py','gateway_native_orders.py','gateway_book_routes.py','gateway_read_sequence.py','gateway_concurrent_ws.py','gateway_account_ws.py','gateway_market_ws.py','gateway_snapshot_ws.py','portfolio_ws_frames.py','ledger_gateway.py','selftest.py','portfolio_rate_evidence.py','portfolio_tls_provenance.py','portfolio_egress_ledger.py'):
    path=code/name
    assert path.read_bytes()
    denied('write:'+name,lambda:os.open(path,os.O_WRONLY))
    denied('unlink:'+name,lambda:os.unlink(path))
    denied('chmod:'+name,lambda:os.chmod(path,0o644))
for path in (Path('/etc/trader/egress-gateway-fixture.json'),Path('/run/trader-egress-gateway-fixture.json'),Path('/var/lib/trader/egress/local-egress-attempts-v1/events.jsonl'),Path('/var/lib/trader/egress/local-egress-attempts-v1/kernel.jsonl')):
    denied('read:'+path.name,lambda:os.open(path,os.O_RDONLY))
    denied('write:'+path.name,lambda:os.open(path,os.O_WRONLY))
    denied('unlink:'+path.name,lambda:os.unlink(path))
denied('create_alternative_scope',lambda:os.mkdir('/var/lib/trader/egress/replacement'))
with socket.socket() as s:
    denied('forge_socket_mark',lambda:s.setsockopt(socket.SOL_SOCKET,socket.SO_MARK,29810))
with socket.socket() as s:
    s.settimeout(0.3)
    try: s.connect(('198.51.100.2',23456))
    except (TimeoutError,PermissionError): checks.append('unmarked_egress_denied')
    else: raise RuntimeError('unmarked_egress_allowed')
status=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines())
assert os.getuid()!=0 and status['Groups'].strip()=='' and status['NoNewPrivs'].strip()=='1'
assert all(int(status[k],16)==0 for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
print(json.dumps({'checks':checks,'uid':os.getuid(),'gid':os.getgid()}))
"""


TLS_PEER = (
    "FIXTURE_ORDERS="
    + repr(FIXTURE_ORDERS)
    + "\nFIXTURE_BOOKS="
    + repr(FIXTURE_BOOKS)
    + "\n"
    + r"""
import hashlib,json,os,socket,ssl,sys,time
scenario=sys.argv[1]
if scenario.startswith('routes_ws_') or scenario.startswith('snapshot_'):scenario='routes_two_hops' if scenario in {'routes_ws_two_hops','snapshot_two_hops'} else 'routes_success'
body=json.dumps({'rateLimits':[
 {'rateLimitType':'REQUEST_WEIGHT','interval':'MINUTE','intervalNum':1,'limit':6000},
 {'rateLimitType':'RAW_REQUESTS','interval':'MINUTE','intervalNum':5,'limit':61000},
 {'rateLimitType':'CONNECTIONS','interval':'MINUTE','intervalNum':5,'limit':300}
]},separators=(',',':')).encode()
if sys.argv[2]=='native':
    metadata=json.loads(body)
    metadata['symbols']=[{'symbol':asset+'USDT','baseAsset':asset,'baseAssetPrecision':17 if scenario=='native_precision' and asset=='BTC' else 7 if scenario=='sequence_metadata_mismatch' and asset=='BTC' else 8,'quoteAsset':'USDT','quoteAssetPrecision':8} for asset in ('BTC','ETH','BNB')]
    if scenario.startswith('routes_'):
        for row in metadata['symbols']:
            row.update(status='BREAK' if scenario=='routes_disabled' and row['baseAsset']=='BTC' or scenario=='routes_two_hops' and row['baseAsset']=='BNB' else 'TRADING',isSpotTradingAllowed=True)
        if scenario=='routes_two_hops':metadata['symbols'].append({'symbol':'BNBBTC','baseAsset':'BNB','quoteAsset':'BTC','baseAssetPrecision':8,'quoteAssetPrecision':8,'status':'TRADING','isSpotTradingAllowed':True})
    body=json.dumps(metadata,separators=(',',':')).encode()
if sys.argv[2]=='account':
    body=json.dumps({'uid':41001,'accountType':'SPOT','balances':[
        {'asset':'BTC','free':'0.000000001' if scenario=='native_precision' else '0.02000000' if scenario=='sequence_balance_drift' else '0.01000000','locked':'0.00100000'},
        {'asset':'ETH','free':'0.00000000','locked':'0.00000000'},
        {'asset':'BNB','free':'1.00000000','locked':'0.10000000'},
        {'asset':'USDT','free':'500.00000000','locked':'12.50000000'}]},separators=(',',':')).encode()
if scenario=='orders_empty' and sys.argv[2]=='account':
    value=json.loads(body)
    for row in value['balances']:row['locked']='0.00000000'
    body=json.dumps(value,separators=(',',':')).encode()
if sys.argv[2]=='orders':
    value=FIXTURE_ORDERS
    if scenario=='orders_empty': value=[]
    elif scenario=='orders_changed': value[0]['orderId']=104
    elif scenario=='orders_precision': value[0]['origQty']='0.001000001'
    elif scenario=='orders_duplicate': value.append(value[0])
    elif scenario=='orders_lock_mismatch': value[0]['price']='12501.00000000'
    body=json.dumps(value,separators=(',',':')).encode()
if sys.argv[2]=='books':
    value=FIXTURE_BOOKS
    if scenario=='routes_missing':value=value[1:]
    elif scenario=='routes_depth':value[0]['bidQty']='0.01099999'
    elif scenario=='routes_precision':value[0]['bidPrice']='60000.000000001'
    elif scenario=='routes_duplicate':value.append(value[0])
    elif scenario=='routes_two_hops':value.append({'symbol':'BNBBTC','bidPrice':'0.004','askPrice':'0.005','bidQty':'10','askQty':'10'})
    body=json.dumps(value,separators=(',',':')).encode()
headers=b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\nX-MBX-USED-WEIGHT-1M: 20\r\n'
if scenario=='tls_duplicate_weight': headers+=b'x-mbx-used-weight-1m: 20\r\n'
headers+=b'Connection: close\r\n\r\n'
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('/etc/trader/egress-gateway-fixture-ca.pem','/run/gateway-tls-key.pem')
report={'tls_connections':0,'http_requests':0,'request_sha256':None}
def save():
    with open('/run/gateway-tls-peer.json','w') as out:
        json.dump(report,out,sort_keys=True)
        out.flush();os.fsync(out.fileno())
with socket.socket() as listener:
    listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(('198.51.100.2',23456));listener.listen(1);listener.settimeout(10)
    print('ready',flush=True)
    raw,_=listener.accept();report['tls_connections']=1;save()
    try:
        with context.wrap_socket(raw,server_side=True) as connection:
            connection.settimeout(5)
            request=b''
            while b'\r\n\r\n' not in request:
                chunk=connection.recv(4096)
                if not chunk: raise ValueError('no_request')
                request+=chunk
                if len(request)>4096: raise ValueError('request_limit')
            expected=b'GET /api/v3/exchangeInfo HTTP/1.1\r\nHost: rest.fixture.invalid:23456\r\nConnection: close\r\n\r\n'
            if sys.argv[2]=='books':expected=b'GET /api/v3/ticker/bookTicker HTTP/1.1\r\nHost: rest.fixture.invalid:23456\r\nConnection: close\r\n\r\n'
            if sys.argv[2] in {'account','orders'}:
                from urllib.parse import parse_qsl,urlencode
                path='/api/v3/openOrders' if sys.argv[2]=='orders' else '/api/v3/account'
                lines=request.decode('ascii').split('\r\n')
                if len(lines)!=6 or not lines[0].startswith('GET '+path+'?') or not lines[0].endswith(' HTTP/1.1'):
                    raise ValueError('account_request_line')
                query=lines[0][len('GET '+path+'?'):-len(' HTTP/1.1')]
                params=parse_qsl(query,strict_parsing=True)
                if [k for k,v in params]!=['timestamp','recvWindow','signature'] or params[1][1]!='5000' or urlencode(params)!=query:
                    raise ValueError('account_request_params')
                if not params[0][1].isdigit() or not 0<=time.time_ns()//1000000-int(params[0][1])<=5000:
                    raise ValueError('account_request_expired')
                scope={'__name__':'fixture_signature_verifier'}
                exec(compile(open('/usr/local/lib/trader-egress/gateway_native_requests.py').read(),'<held-fixture-verifier>','exec'),scope)
                scope['verify_signature'](urlencode(params[:-1]),params[-1][1])
                expected=('GET '+path+'?'+query+' HTTP/1.1\r\nHost: rest.fixture.invalid:23456\r\nX-MBX-APIKEY: '+scope['API_KEY']+'\r\nConnection: close\r\n\r\n').encode()
                report['native_signature_verified']=True
            if request!=expected: raise ValueError('unexpected_request')
            report['http_requests']=1;report['request_sha256']=hashlib.sha256(request).hexdigest();save()
            connection.sendall(headers)
            if scenario in {'tls_slow_body','tls_crash'}: time.sleep(1.2 if scenario=='tls_slow_body' else 2)
            connection.sendall(body[:5] if scenario=='tls_truncated' else body)
    except (ssl.SSLError,OSError,ValueError) as exc:
        report['ended_with']=type(exc).__name__;save()
"""
)


WS_PEER = r"""
import base64,hashlib,json,os,socket,ssl,sys,threading,time
scenario=sys.argv[1]
context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain('/etc/trader/egress-gateway-fixture-ca.pem','/run/gateway-tls-key.pem')
names={}
context.set_servername_callback(lambda connection,name,ctx:names.update({id(connection):name}))
barrier=threading.Barrier(2,timeout=2.5)
lock=threading.Lock()
report={'connections':0,'upgrades':0,'pongs':0,'closes':0,'both_upgrades_before_ping':False,'requests':{},'snapshot_requests':[],'errors':[]}
def frame(op,data):return bytes([0x80|op])+(bytes([len(data)]) if len(data)<126 else b"\x7e"+len(data).to_bytes(2,"big"))+data
def exact(connection,n):
    raw=b''
    while len(raw)<n:
        chunk=connection.recv(n-len(raw))
        if not chunk:raise ValueError('eof')
        raw+=chunk
    return raw
def control(connection,op,expected):
    head=exact(connection,2)
    if head!=bytes([0x80|op,0x80|len(expected)]):raise ValueError('masked_control_header')
    mask=exact(connection,4);data=exact(connection,len(expected))
    if bytes(v^mask[i%4] for i,v in enumerate(data))!=expected:raise ValueError('masked_control_payload')
def serve(raw):
    try:
        with context.wrap_socket(raw,server_side=True) as connection:
            connection.settimeout(5)
            name=names[id(connection)]
            role=name.split('.')[0]
            if role not in {'account','market','rest'}:raise ValueError('sni')
            request=b''
            while b'\r\n\r\n' not in request:
                request+=connection.recv(4096)
                if len(request)>4096:raise ValueError('header_limit')
                if not request:raise ValueError('no_request')
            if role=='rest':
                symbols=['BNBBTC','BTCUSDT'] if scenario=='snapshot_two_hops' else ['BNBUSDT','BTCUSDT']
                symbol=next((s for s in symbols if request==f'GET /api/v3/depth?symbol={s}&limit=100 HTTP/1.1\r\nHost: rest.fixture.invalid:23456\r\nConnection: close\r\n\r\n'.encode()),None)
                if symbol is None:raise ValueError('snapshot_fixed_request')
                with lock:report['snapshot_requests'].append(symbol)
                body=json.dumps({'lastUpdateId':104 if scenario=='snapshot_gap' else 'bad' if scenario=='snapshot_bad_http' else 101,'bids':[['100.00000000','1.00000000']],'asks':[['101.00000000','2.00000000']]},separators=(',',':')).encode()
                response=b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\nX-MBX-USED-WEIGHT-1M: 25\r\nConnection: close\r\n\r\n'+body
                connection.sendall(response[:45]);connection.sendall(response[45:]);return
            lines=request.decode().split('\r\n')
            nonce=next(line.split(': ',1)[1] for line in lines if line.startswith('Sec-WebSocket-Key: '))
            if len(base64.b64decode(nonce,validate=True))!=16:raise ValueError('nonce')
            symbols=['BNBBTC','BTCUSDT'] if scenario in {'routes_ws_two_hops','snapshot_two_hops'} else ['BNBUSDT','BTCUSDT']
            path='/ws-api/v3' if role=='account' else '/stream?streams='+'/'.join(s.lower()+'@depth@100ms' for s in symbols)
            expected=(f'GET {path} HTTP/1.1\r\nHost: {role}.fixture.invalid:23456\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {nonce}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode()
            if request!=expected:raise ValueError('fixed_request')
            with lock:
                if role in report['requests']:raise ValueError('duplicate_role')
                report['requests'][role]=hashlib.sha256(request).hexdigest()
            barrier.wait()
            accept=base64.b64encode(hashlib.sha1(nonce.encode()+b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
            if scenario=='routes_ws_bad_upgrade' and role=='market':accept=b'invalid'
            headers=b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: '+accept+b'\r\n\r\n'
            connection.sendall(headers[:31]);connection.sendall(headers[31:])
            with lock:report['upgrades']+=1
            barrier.wait()
            with lock:report['both_upgrades_before_ping']=report['upgrades']==2
            if scenario=='routes_ws_stall':time.sleep(4.5);return
            if scenario=='routes_ws_peer_close' and role=='market':connection.sendall(frame(8,b'\x03\xe8'));return
            ping=frame(9,b'fixture:'+role.encode())
            connection.sendall(ping[:3]);connection.sendall(ping[3:])
            control(connection,10,b'fixture:'+role.encode())
            with lock:report['pongs']+=1
            if sys.argv[2] in {'signed','market','snapshot'} and role=='account':
                head=exact(connection,2)
                if head[0]!=0x81 or not head[1]&0x80:raise ValueError('signed_text_required')
                size=head[1]&127
                if size==126:size=int.from_bytes(exact(connection,2),'big')
                if size>850:raise ValueError('signed_text_limit')
                mask=exact(connection,4);encoded=exact(connection,size)
                payload=bytes(v^mask[i%4] for i,v in enumerate(encoded));request=json.loads(payload)
                scope={'__name__':'fixture_verifier'}
                exec(compile(open('/usr/local/lib/trader-egress/gateway_native_requests.py').read(),'<fixture-verifier>','exec'),scope)
                params=request['params'];signature=params.pop('signature')
                if set(request)!={'id','method','params'} or request['id']!='fixture-2' or request['method']!='userDataStream.subscribe.signature':raise ValueError('subscription_selector')
                if set(params)!={'apiKey','recvWindow','timestamp'} or params['apiKey']!=scope['API_KEY'] or params['recvWindow']!=5000 or not 0<=time.time_ns()//1000000-params['timestamp']<5000:raise ValueError('subscription_parameters')
                scope['verify_signature']('&'.join(str(k)+'='+str(v) for k,v in sorted(params.items())),signature)
                with lock:report['subscription_signature_verified']=True
                reply={'id':'fixture-2','status':200,'result':{'subscriptionId':0}}
                if scenario=='routes_ws_bad_response':reply['id']='foreign'
                now=time.time_ns()//1000000
                update={'subscriptionId':0,'event':{'e':'outboundAccountPosition','E':now,'u':now,'B':[{'a':'BTC','f':'0.01000000','l':'0.00100000'}]}}
                if scenario=='routes_ws_wrong_subscription':update['subscriptionId']=1
                if scenario=='routes_ws_precision':update['event']['B'][0]['f']='0.010000001'
                reply_raw=json.dumps(reply,separators=(',',':')).encode();event_raw=json.dumps(update,separators=(',',':')).encode()
                connection.sendall(frame(1,reply_raw))
                # Fragment the original event across continuation frames and TLS writes.
                first=frame(1,event_raw[:50]);first=bytes([1])+first[1:]
                connection.sendall(first[:7]);connection.sendall(first[7:]+frame(0,event_raw[50:]))
                if scenario=='routes_ws_extra_event':connection.sendall(frame(1,event_raw))
            if sys.argv[2] in {'market','snapshot'} and role=='market':
                sent=0
                for index in range(2):
                    for symbol in symbols:
                        if scenario=='routes_ws_missing_symbol' and symbol==symbols[-1]:continue
                        now=time.time_ns()//1000000
                        event={'stream':symbol.lower()+'@depth@100ms','data':{'e':'depthUpdate','E':now,'s':symbol,'U':100+index*2,'u':101+index*2,'b':[['100.00000000','1.10000000' if index==0 else '0.00000000']],'a':[['101.00000000','2.00000000']]}}
                        if index==1 and scenario=='routes_ws_overlap':event['data']['U']=101
                        if index==1 and scenario=='routes_ws_gap':event['data']['U']=104;event['data']['u']=105
                        if index==1 and scenario=='routes_ws_duplicate_update':event['data']['U']=100;event['data']['u']=101
                        if scenario=='routes_ws_wrong_stream':event['stream']='foreign@depth@100ms'
                        if scenario=='routes_ws_market_precision':event['data']['b'][0][0]='100.000000001'
                        raw=json.dumps(event,separators=(',',':')).encode()
                        first=frame(1,raw[:30]);first=bytes([1])+first[1:]
                        connection.sendall(first[:5]);connection.sendall(first[5:]+frame(0,raw[30:]))
                        sent+=1
                if scenario=='routes_ws_extra_market':connection.sendall(frame(1,raw));sent+=1
                with lock:report['market_events_sent']=sent
            if sys.argv[2] in {'market','snapshot'}:barrier.wait()
            control(connection,8,b'\x03\xe8')
            with lock:report['closes']+=1
            connection.sendall(frame(8,b'\x03\xe8'))
    except Exception as exc:
        with lock:report['errors'].append(type(exc).__name__+':'+str(exc)[:100])
    finally:raw.close()
threads=[]
with socket.socket() as listener:
    listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    listener.bind(('198.51.100.2',23456));listener.listen(4);listener.settimeout(5)
    print('ready',flush=True)
    try:
        for _ in range(4 if sys.argv[2]=='snapshot' else 2):
            raw,_=listener.accept();report['connections']+=1
            thread=threading.Thread(target=serve,args=(raw,));thread.start();threads.append(thread)
    except Exception as exc:report['errors'].append(type(exc).__name__)
    for thread in threads:thread.join()
with open('/run/gateway-ws-peer.json','w') as out:
    json.dump(report,out,sort_keys=True);out.flush();os.fsync(out.fileno())
"""


def worker(payload):
    base = load(payload["base_source"])
    base["require_isolation"](payload["original"])
    requests = payload.get("native_requests_profile", False)
    snapshot_ws = payload.get("snapshot_ws_profile", False)
    market_ws = payload.get("market_ws_profile", False) or snapshot_ws
    signed_ws = payload.get("signed_ws_profile", False) or market_ws
    concurrent = payload.get("concurrent_ws_profile", False) or signed_ws
    routes = payload.get("route_sequence_profile", False) or concurrent
    orders = payload.get("order_sequence_profile", False) or routes
    sequence = payload.get("read_sequence_profile", False) or orders
    signed = payload.get("signed_account_profile", False)
    native = payload.get("native_receipt_profile", False) or signed or sequence
    receipt = payload.get("tls_receipt_profile", False) or native
    tls = payload.get("tls_profile", False) or receipt
    ipc = payload.get("joint_ipc_profile", False) or requests
    if (
        type(concurrent) is not bool
        or type(routes) is not bool
        or type(orders) is not bool
        or type(sequence) is not bool
        or type(signed) is not bool
        or type(requests) is not bool
        or type(native) is not bool
        or type(receipt) is not bool
        or type(tls) is not bool
        or type(ipc) is not bool
        or (tls and ipc)
        or payload["scenario"]
        not in (
            SNAPSHOT_WS_SCENARIOS
            if snapshot_ws
            else MARKET_WS_SCENARIOS
            if market_ws
            else SIGNED_WS_SCENARIOS
            if signed_ws
            else WS_SCENARIOS
            if concurrent
            else ROUTE_SCENARIOS
            if routes
            else ORDER_SCENARIOS
            if orders
            else SEQUENCE_SCENARIOS
            if sequence
            else REQUEST_SCENARIOS
            if requests
            else IPC_SCENARIOS
            if ipc
            else NATIVE_SCENARIOS
            if native
            else RECEIPT_SCENARIOS
            if receipt
            else TLS_SCENARIOS
            if tls
            else SCENARIOS
        )
    ):
        raise ValueError("unknown_fixture_scenario")
    # The existing pinned installer and its 40 checks run before extension staging.
    installed = base["worker"](payload)
    signal.alarm(60)
    run, write = base["run"], base["write"]
    entry = load(payload["sources"]["installed_gateway.py"])
    if set(payload["sources"]) != set(entry["FILES"]):
        raise ValueError("fixture_source_inventory")
    pins = {name: base["sha"](raw.encode()) for name, raw in payload["sources"].items()}
    if pins != payload["source_sha256"]:
        raise ValueError("fixture_source_selection")
    for name in entry["FILES"]:
        write(entry["CODE"] + "/" + name, payload["sources"][name].encode(), 0o444)
    base_manifest = Path("/etc/trader/egress-install.json").read_bytes()
    manifest = {
        "schema_version": entry["PROFILE"],
        "base_manifest_sha256": base["sha"](base_manifest),
        "files": pins,
    }
    write(entry["MANIFEST"], json.dumps(manifest, sort_keys=True).encode(), 0o600)
    write(
        entry["CONTEXT"],
        json.dumps(
            {
                "profile": entry["PROFILE"],
                "original": payload["original"],
                "isolated": base["namespaces"](),
            },
            sort_keys=True,
        ).encode(),
        0o600,
    )
    native_runtime = None
    if native or requests:
        native_runtime = load(payload["sources"]["gateway_native_runtime.py"])["stage"](
            base64.b64decode(payload["native_bundle"], validate=True),
            payload["native_bundle_sha256"],
            run,
        )
    guards = load(payload["sources"]["selftest.py"])
    gateway = load(payload["sources"]["ledger_gateway.py"])
    ledger_module = gateway["load_ledger"](payload["sources"])
    account_code = load(payload["sources"]["gateway_native_account.py"]) if signed else None
    if signed:
        ledger_module = account_code["ledger_view"](ledger_module)
    rates = (
        account_code["rates_view"]()
        if signed
        else sys.modules["apps.strategies_nautilus.portfolio_rate_evidence"]
    )
    peer = guards["Child"](payload["sources"]["selftest.py"])
    controller = tls_peer = None
    try:
        ip, nft, network_run = guards["IP"], guards["NFT"], guards["run"]
        network_run(ip, "link", "set", "lo", "up")
        network_run(ip, "link", "add", "wan", "type", "veth", "peer", "name", "peer")
        network_run(ip, "link", "set", "peer", "netns", str(peer.process.pid))
        network_run(ip, "link", "set", "wan", "up")
        network_run(ip, "address", "add", "198.51.100.1/24", "dev", "wan")
        peer.ip("link", "set", "peer", "up")
        for address in ("198.51.100.2/24", "198.51.100.3/24"):
            peer.ip("address", "add", address, "dev", "peer")
        for address in ("fd00:7472:2::2/64", "fd00:7472:2::3/64"):
            peer.ip("-6", "address", "add", address, "dev", "peer", "nodad")
        if tls:
            hostname = (
                "wrong.fixture.invalid"
                if payload["scenario"] == "tls_bad_certificate"
                else "rest.fixture.invalid"
            )
            run(
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-config",
                "/dev/null",
                "-subj",
                "/CN=" + hostname,
                "-addext",
                "subjectAltName=DNS:"
                + hostname
                + (
                    ",DNS:account.fixture.invalid,DNS:market.fixture.invalid"
                    if concurrent and payload["scenario"] != "routes_ws_bad_certificate"
                    else ""
                ),
                "-keyout",
                "/run/gateway-tls-key.pem",
                "-out",
                "/etc/trader/egress-gateway-fixture-ca.pem",
            )
            Path("/etc/trader/egress-gateway-fixture-ca.pem").chmod(0o444)
            Path("/run/gateway-tls-key.pem").chmod(0o600)
            tls_peer = subprocess.Popen(
                [
                    "/usr/bin/nsenter",
                    f"--net=/proc/{peer.process.pid}/ns/net",
                    "/usr/bin/setpriv",
                    "--bounding-set=-all",
                    "--inh-caps=-all",
                    "--ambient-caps=-all",
                    "--no-new-privs",
                    "/usr/bin/python3",
                    "-I",
                    "-c",
                    TLS_PEER,
                    payload["scenario"],
                    "account" if signed else "native" if native else "stdlib",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=ENV,
                cwd="/",
            )
            if tls_peer.stdout.readline().strip() != "ready":
                raise RuntimeError("tls_peer_failed:" + tls_peer.stderr.read()[-2000:])
        elif peer.request({"action": "serve"}) != {"ok": True}:
            raise RuntimeError("fixture_peer_not_ready")
        network_run(nft, "-f", "-", text=gateway["RULES"])
        if ipc:
            return worker_ipc(
                payload,
                installed,
                entry,
                guards,
                ledger_module,
                manifest,
                native_runtime=native_runtime,
            )
        if sequence:
            return worker_sequence(
                payload, installed, entry, guards, manifest, native_runtime, tls_peer, peer
            )
        command = [
            "/usr/bin/python3",
            "-I",
            entry["CODE"] + "/installed_gateway.py",
            "--signed-account-fixture"
            if signed
            else "--native-receipt-fixture"
            if native
            else "--tls-receipt-fixture"
            if receipt
            else "--tls-fixture"
            if tls
            else "--fixture",
        ]
        controller = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=ENV,
            cwd="/",
        )
        line = controller.stdout.readline()
        if not line:
            raise RuntimeError("installed_controller_not_ready:" + controller.stderr.read()[-3000:])
        ready = json.loads(line)
        if ready["stage"] != "activated":
            raise RuntimeError("installed_controller_wrong_stage")
        identity = ready["binding"]["collector"]["process"]
        account = installed["fixture_account"]
        if (
            identity["uids"] != [account["uid"]] * 4
            or identity["gids"] != [account["gid"]] * 4
            or identity["groups"]
        ):
            raise RuntimeError("installed_collector_identity")
        descriptors = [os.readlink(p) for p in Path(f"/proc/{identity['pid']}/fd").iterdir()]
        if any(
            any(
                prefix in target
                for prefix in ("/var/lib/trader", entry["CODE"], "/etc/trader", entry["CONTEXT"])
            )
            for target in descriptors
        ):
            raise RuntimeError("privileged_file_descriptor_inherited")
        checks = [
            "fixed_root_owned_sources_and_manifest_loaded",
            "distinct_uid_authenticated_before_preparation",
            "collector_has_no_privileged_file_descriptors",
        ]

        def denied_counter():
            rows = json.loads(
                network_run(
                    nft, "-j", "list", "counter", "inet", "fixture_ledger_gateway", "output_denied"
                )
            )
            return next(row["counter"]["packets"] for row in rows["nftables"] if "counter" in row)

        before = denied_counter()
        probe = json.loads(
            run(
                "/usr/bin/setpriv",
                f"--reuid={account['uid']}",
                f"--regid={account['gid']}",
                "--clear-groups",
                "--bounding-set=-all",
                "--inh-caps=-all",
                "--ambient-caps=-all",
                "--no-new-privs",
                "/usr/bin/python3",
                "-I",
                "-c",
                PROBE.replace("local-egress-attempts-v1", ledger_module.SCOPE),
            )
        )
        if (probe["uid"], probe["gid"]) != (
            account["uid"],
            account["gid"],
        ) or denied_counter() <= before:
            raise RuntimeError("dedicated_uid_or_packet_denial_missing")
        checks.extend(probe["checks"])
        scenario = payload["scenario"]
        restore = None
        if scenario == "code_drift":
            target = Path(entry["CODE"]) / "ledger_gateway.py"
            original = target.read_bytes()
            target.write_bytes(original + b"\n# injected fixture drift\n")

            def restore():
                target.write_bytes(original)
        elif scenario == "account_drift":
            target = Path("/etc/group")
            original = target.read_bytes()
            target.write_bytes(original + b"foreign:x:22000:trader-egress\n")

            def restore():
                target.write_bytes(original)
        elif scenario == "storage_drift":
            target = Path(entry["STORAGE"])
            target.chmod(0o755)

            def restore():
                target.chmod(0o700)

        stopped_fd = None
        late_receipt = scenario.startswith("receipt_")
        if late_receipt:
            controller.stdin.write("continue\n")
            controller.stdin.flush()
            for stage in ("tls_headers_persisted", "receipt_prepared"):
                if json.loads(controller.stdout.readline()) != {"stage": stage}:
                    raise RuntimeError("receipt_barrier_missing")
            rows = json.loads(
                network_run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
            )
            if any(row.get("set", {}).get("elem") for row in rows["nftables"]):
                raise RuntimeError("receipt_wait_retained_permission")
            checks.append("kernel_revoked_before_receipt_wait")
            if scenario == "receipt_child_death":
                child_fd = os.pidfd_open(identity["pid"])
                try:
                    signal.pidfd_send_signal(child_fd, signal.SIGKILL)
                    if not select.select([child_fd], [], [], 2)[0]:
                        raise RuntimeError("receipt_child_not_dead")
                finally:
                    os.close(child_fd)
            elif scenario == "receipt_child_stopped":
                stopped_fd = os.pidfd_open(identity["pid"])
                signal.pidfd_send_signal(stopped_fd, signal.SIGSTOP)
                stopped = False
                for _ in range(100):
                    status = Path(f"/proc/{identity['pid']}/status").read_text()
                    if any(line.startswith("State:\tT") for line in status.splitlines()):
                        stopped = True
                        break
                    time.sleep(0.01)
                if not stopped:
                    raise RuntimeError("receipt_child_not_stopped")
                checks.append("receipt_consumer_sigstop_observed")
            elif scenario == "receipt_runtime_drift":
                native_root = "/run/trader-native-runtime"
                run("/usr/bin/mount", "-o", "remount,rw,nosuid,nodev", native_root)

                def restore():
                    run("/usr/bin/mount", "-o", "remount,ro,nosuid,nodev", native_root)

                checks.append("native_runtime_mount_drift_injected")
            elif scenario == "receipt_code_drift":
                target = Path(entry["CODE"]) / "gateway_tls_receipt.py"
                original = target.read_bytes()
                target.write_bytes(original + b"\n# fixture drift\n")

                def restore():
                    target.write_bytes(original)
            elif scenario == "receipt_storage_drift":
                target = Path(entry["STORAGE"])
                target.chmod(0o755)

                def restore():
                    target.chmod(0o700)

        if scenario == "receipt_controller_crash":
            orphan_fd = os.pidfd_open(identity["pid"])
            controller.kill()
            controller.communicate(timeout=5)
            try:
                if (
                    controller.returncode != -signal.SIGKILL
                    or not select.select([orphan_fd], [], [], 5)[0]
                ):
                    raise RuntimeError("receipt_controller_or_orphan_survived")
                os.waitpid(identity["pid"], 0)
            finally:
                os.close(orphan_fd)
            terminal = {"status": "controller_sigkill", "revoked": True}
            checks.append("receipt_controller_death_exits_child_with_no_kernel_permit")
        elif scenario in {"controller_crash", "tls_crash"}:
            if tls:
                controller.stdin.write("continue\n")
                controller.stdin.flush()
                if json.loads(controller.stdout.readline()) != {"stage": "tls_headers_persisted"}:
                    raise RuntimeError("tls_crash_header_persistence_not_acknowledged")
            controller.kill()
            stdout, stderr = controller.communicate(timeout=5)
            if controller.returncode != -signal.SIGKILL:
                raise RuntimeError("controller_sigkill_failed")
            rows = json.loads(
                network_run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
            )
            if not any(row.get("set", {}).get("elem") for row in rows["nftables"]):
                raise RuntimeError("crash_permission_not_observed")
            time.sleep(5.2)
            terminal = {"status": "controller_sigkill", "revoked": None}
            checks.append("controller_death_retains_permit_until_kernel_expiry")
        else:
            stdout, stderr = controller.communicate(
                "continue\ncontinue\n" if receipt and not late_receipt else "continue\n", timeout=10
            )
            if controller.returncode:
                raise RuntimeError("installed_controller_failed:" + stderr[-3000:])
            messages = [json.loads(line) for line in stdout.splitlines()]
            expected_progress = (
                [{"stage": "tls_headers_persisted"}]
                if tls and scenario != "tls_bad_certificate"
                else []
            )
            if receipt and scenario in {"tls_success", "tls_slow_body", "native_precision"}:
                expected_progress.append({"stage": "receipt_prepared"})
            if late_receipt:
                expected_progress = []
            if not messages or messages[:-1] != expected_progress:
                raise RuntimeError("unexpected_controller_progress")
            terminal = messages[-1]
            if (
                terminal["status"]
                != (
                    ("fixture_receipt_succeeded" if receipt else "fixture_tls_succeeded")
                    if scenario in {"tls_success", "tls_slow_body"}
                    else "fixture_echo_succeeded"
                    if scenario == "success"
                    else "refused"
                )
                or not terminal["revoked"]
            ):
                raise RuntimeError("wrong_installed_gateway_outcome")
        if stopped_fd is not None:
            try:
                if (
                    terminal.get("reason") != "TimeoutError"
                    or not select.select([stopped_fd], [], [], 1)[0]
                ):
                    raise RuntimeError("receipt_stalled_child_timeout_or_cleanup_missing")
                if Path(f"/proc/{identity['pid']}").exists():
                    raise RuntimeError("receipt_stalled_child_not_reaped")
                checks.append("receipt_timeout_kills_and_reaps_stopped_consumer")
            finally:
                os.close(stopped_fd)
        if restore is not None:
            restore()
        before = denied_counter()
        try:
            gateway["marked_echo"]()
        except OSError:
            pass
        else:
            raise RuntimeError("marked_socket_not_denied_after_terminal")
        if denied_counter() <= before:
            raise RuntimeError("terminal_deny_counter_missing")
        checks.append("marked_socket_kernel_denied_after_terminal_or_expiry")
        scope = Path(entry["STORAGE"]) / ledger_module.SCOPE
        attempts, lifecycle = (
            (scope / "events.jsonl").read_bytes(),
            (scope / "kernel.jsonl").read_bytes(),
        )
        attempt_report = ledger_module.replay(
            attempts,
            expected_sha256=ledger_module.digest(attempts),
            binding_sha256=ready["binding_sha256"],
        )
        life_report = gateway["replay_lifecycle"](
            ledger_module,
            lifecycle,
            expected_sha256=ledger_module.digest(lifecycle),
            attempts=attempts,
            binding_sha256=ready["binding_sha256"],
        )
        if attempt_report["pending_attempt"] != (
            None if scenario in {"success", "tls_success", "tls_slow_body"} else 0
        ):
            raise RuntimeError("pending_attempt_lost")
        if life_report["revocation_recorded"] != (
            scenario not in {"controller_crash", "storage_drift", "tls_crash"}
        ):
            raise RuntimeError("invented_or_missing_revocation_record")
        tls_result = {}
        if tls:
            raw_tls = (scope / "tls.jsonl").read_bytes()
            transport = load(payload["sources"]["gateway_tls.py"])
            selection_raw = None
            if signed:
                selection_raw = (scope / "account-request.json").read_bytes()
                contract = account_code["AccountContract"](
                    load(payload["sources"]["gateway_native_requests.py"]),
                    json.loads(selection_raw),
                )
                if contract.raw != selection_raw:
                    raise RuntimeError("noncanonical_signed_account_selection")
                transport = account_code["transport_view"](transport, contract)
            trust = Path("/etc/trader/egress-gateway-fixture-ca.pem").read_bytes()
            replay = transport["replay"](
                raw_tls,
                expected_sha256=base["sha"](raw_tls),
                attempts=attempts,
                lifecycle=lifecycle,
                binding_sha256=ready["binding_sha256"],
                trust_sha256=base["sha"](trust),
                ledger_module=ledger_module,
                gateway_module=gateway,
                provenance=sys.modules["apps.strategies_nautilus.portfolio_tls_provenance"],
                rates=rates,
            )
            if (replay["status"] == "complete") != (
                scenario in {"tls_success", "tls_slow_body", "native_precision"} or late_receipt
            ):
                raise RuntimeError("tls_replay_completion_mismatch")
            if scenario == "tls_slow_body" and replay["header_age_at_body_ns"] < 1_000_000_000:
                raise RuntimeError("tls_header_receipt_refreshed")
            tls_peer.wait(timeout=5)
            peer_report = json.loads(Path("/run/gateway-tls-peer.json").read_bytes())
            if peer_report["tls_connections"] != 1 or peer_report["http_requests"] != (
                0 if scenario == "tls_bad_certificate" else 1
            ):
                raise RuntimeError("tls_peer_request_count_mismatch")
            checks.append("fixed_tls_request_and_original_header_receipt_verified")
            tls_result = {
                "tls_archive": raw_tls.decode(),
                "tls_replay": replay,
                "tls_trust_sha256": base["sha"](trust),
                "tls_trust_pem": trust.decode(),
                "tls_peer": peer_report,
                **(
                    {
                        "account_selection": selection_raw.decode(),
                        "account_selection_sha256": base["sha"](selection_raw),
                    }
                    if signed
                    else {}
                ),
            }
            if signed and scenario != "tls_bad_certificate":
                if not peer_report.get("native_signature_verified") or peer_report[
                    "request_sha256"
                ] != base["sha"](contract.request):
                    raise RuntimeError("peer_signed_account_request_mismatch")
                checks.append("native_signed_request_matches_independent_tls_peer_verification")
        if receipt and (scope / "receipt.jsonl").exists():
            receipt_code = load(payload["sources"]["gateway_tls_receipt.py"])
            receipt_raw = (scope / "receipt.jsonl").read_bytes()
            receipt_replay = receipt_code["replay"](
                receipt_raw,
                expected_sha256=base["sha"](receipt_raw),
                native=account_code
                if signed
                else load(payload["sources"]["gateway_native_receipt.py"])
                if native
                else None,
                tls_raw=raw_tls,
                attempts=attempts,
                lifecycle=lifecycle,
                trust_sha256=base["sha"](trust),
                ledger_module=ledger_module,
                gateway_module=gateway,
                transport=transport,
                provenance=sys.modules["apps.strategies_nautilus.portfolio_tls_provenance"],
                rates=rates,
                binding_sha256=ready["binding_sha256"],
            )
            if (receipt_replay["status"] == "acknowledged") != (
                scenario in {"tls_success", "tls_slow_body"}
            ):
                raise RuntimeError("receipt_acknowledgement_mismatch")
            if native:
                if receipt_replay["schema_version"] != (
                    account_code["PROFILE"] if signed else "portfolio.installed_native_receipt.v1"
                ):
                    raise RuntimeError("native_receipt_profile_missing")
                tls_result["native_runtime"] = native_runtime
            tls_result.update(receipt_archive=receipt_raw.decode(), receipt_replay=receipt_replay)
            checks.append("authenticated_consumer_receipt_replays_with_original_tls_clocks")
        restarted = subprocess.run(
            command,
            input="continue\n",
            capture_output=True,
            text=True,
            env=ENV,
            cwd="/",
            timeout=10,
        )
        if (
            restarted.returncode != 1
            or "FileExistsError" not in restarted.stderr
            or restarted.stdout
        ):
            raise RuntimeError("fresh_installed_process_reopened_consumed_scope")
        if (scope / "events.jsonl").read_bytes() != attempts or (
            scope / "kernel.jsonl"
        ).read_bytes() != lifecycle:
            raise RuntimeError("restart_changed_original_journals")
        if tls and (scope / "tls.jsonl").read_bytes() != raw_tls:
            raise RuntimeError("restart_changed_tls_journal")
        if (
            receipt
            and (scope / "receipt.jsonl").exists()
            and (scope / "receipt.jsonl").read_bytes() != receipt_raw
        ):
            raise RuntimeError("restart_changed_receipt_journal")
        checks.append("fresh_installed_process_refuses_scope_without_changing_journals")
        if (
            Path(entry["STORAGE"] + "/consumed.json").read_bytes()
            != b'{"fixture_only":true,"consumed":true}\n'
        ):
            raise RuntimeError("prior_consumed_fixture_state_changed")
        checks.append("prior_consumed_fixture_state_preserved")
        if any(name.startswith("nautilus_trader") for name in sys.modules):
            raise RuntimeError("native_package_loaded_by_root")
        return {
            "root_native_modules_loaded": False,
            "scenario": scenario,
            "status": "passed",
            **tls_result,
            "checks": checks,
            "base_installation": installed,
            "gateway_manifest": manifest,
            "gateway_manifest_sha256": base["sha"](Path(entry["MANIFEST"]).read_bytes()),
            "binding": ready["binding"],
            "binding_sha256": ready["binding_sha256"],
            "terminal": terminal,
            "attempt_archive": attempts.decode(),
            "lifecycle_archive": lifecycle.decode(),
            "attempt_replay": attempt_report,
            "lifecycle_replay": life_report,
        }
    finally:
        if controller is not None and controller.poll() is None:
            controller.kill()
            controller.communicate(timeout=3)
        if tls_peer is not None and tls_peer.poll() is None:
            tls_peer.kill()
            tls_peer.communicate(timeout=3)
        peer.stop()


def worker_sequence(payload, installed, entry, guards, manifest, native_runtime, tls_peer, peer):
    """Drive fixed barriers only; parent is namespace PID 1 and has no host network."""
    code = load(payload["sources"]["gateway_read_sequence.py"])
    modules = code["load_sources"](payload["sources"])
    snapshot_ws = payload.get("snapshot_ws_profile", False)
    market_ws = payload.get("market_ws_profile", False) or snapshot_ws
    signed_ws = payload.get("signed_ws_profile", False) or market_ws
    concurrent = payload.get("concurrent_ws_profile", False) or signed_ws
    routes = payload.get("route_sequence_profile", False) or concurrent
    orders = payload.get("order_sequence_profile", False) or routes
    steps = code["ROUTE_STEPS"] if routes else code["ORDER_STEPS"] if orders else code["STEPS"]
    scope_name = code["ROUTE_SCOPE"] if routes else code["ORDER_SCOPE"] if orders else code["SCOPE"]
    root = Path(entry["STORAGE"]) / scope_name
    command = [
        "/usr/bin/python3",
        "-I",
        entry["CODE"] + "/installed_gateway.py",
        "--snapshot-ws-fixture"
        if snapshot_ws
        else "--market-ws-fixture"
        if market_ws
        else "--signed-ws-fixture"
        if signed_ws
        else "--concurrent-ws-fixture"
        if concurrent
        else "--route-sequence-fixture"
        if routes
        else "--order-sequence-fixture"
        if orders
        else "--read-sequence-fixture",
    ]
    controller = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=ENV,
        cwd="/",
    )
    checks, peers, bindings, descriptor_counts = [], [], [], []
    scenario = payload["scenario"]
    index = 0
    stopped = None
    restore = None
    ws_peer = None
    ws_result = {}

    def revoked():
        rows = json.loads(
            guards["run"](
                guards["NFT"], "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits"
            )
        )
        if any(row.get("set", {}).get("elem") for row in rows["nftables"]):
            raise RuntimeError("sequence_kernel_permit_retained")

    def release():
        controller.stdin.write("continue\n")
        controller.stdin.flush()

    def finish_peer():
        tls_peer.wait(timeout=5)
        value = json.loads(Path("/run/gateway-tls-peer.json").read_bytes())
        if value["http_requests"] != 1 or (
            index in {1, 2, 3, 4} and not value.get("native_signature_verified")
        ):
            raise RuntimeError("sequence_peer_request_mismatch")
        peers.append(value)

    try:
        while True:
            line = controller.stdout.readline()
            if not line:
                raise RuntimeError(
                    "sequence_controller_no_message:" + controller.stderr.read()[-3000:]
                )
            message = json.loads(line)
            if message.get("stage") in {"activated", "receipt_prepared"}:
                descriptor_counts.append(len(list(Path(f"/proc/{controller.pid}/fd").iterdir())))
            stage = message.get("stage")
            if stage == "activated":
                index = message["binding"]["read_sequence"]["index"]
                if index != len(bindings):
                    raise RuntimeError("sequence_step_order")
                bindings.append(message["binding"])
                identity = message["binding"]["collector"]["process"]
                if (
                    identity["uids"] != [installed["fixture_account"]["uid"]] * 4
                    or identity["gids"] != [installed["fixture_account"]["gid"]] * 4
                    or identity["groups"]
                ):
                    raise RuntimeError("sequence_child_identity")
                if index == 0:
                    probe = json.loads(
                        guards["run"](
                            "/usr/bin/setpriv",
                            f"--reuid={identity['uids'][0]}",
                            f"--regid={identity['gids'][0]}",
                            "--clear-groups",
                            "--bounding-set=-all",
                            "--inh-caps=-all",
                            "--ambient-caps=-all",
                            "--no-new-privs",
                            "/usr/bin/python3",
                            "-I",
                            "-c",
                            PROBE.replace(
                                "local-egress-attempts-v1",
                                scope_name + "/metadata/local-egress-attempts-v1",
                            ),
                        )
                    )
                    checks.extend(probe["checks"])
                else:
                    selected_scenario = (
                        "native_precision"
                        if index == 2 and scenario == "sequence_second_precision"
                        else "sequence_balance_drift"
                        if index == 2 and scenario == "sequence_balance_drift"
                        else "tls_success"
                    )
                    if orders:
                        selected_scenario = (
                            scenario
                            if scenario == "orders_empty"
                            or index == 2
                            and scenario
                            in {"orders_precision", "orders_duplicate", "orders_lock_mismatch"}
                            or index == 3
                            and scenario == "orders_changed"
                            else "tls_success"
                        )
                    if routes:
                        selected_scenario = scenario
                    tls_peer = subprocess.Popen(
                        [
                            "/usr/bin/nsenter",
                            f"--net=/proc/{peer.process.pid}/ns/net",
                            "/usr/bin/setpriv",
                            "--bounding-set=-all",
                            "--inh-caps=-all",
                            "--ambient-caps=-all",
                            "--no-new-privs",
                            "/usr/bin/python3",
                            "-I",
                            "-c",
                            TLS_PEER,
                            selected_scenario,
                            "books"
                            if routes and index == 5
                            else "orders"
                            if orders and index in {2, 3}
                            else "account",
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env=ENV,
                        cwd="/",
                    )
                    if tls_peer.stdout.readline().strip() != "ready":
                        raise RuntimeError(
                            "sequence_peer_not_ready:" + tls_peer.stderr.read()[-2000:]
                        )
                release()
            elif stage == "ws_prepared":
                revoked()
                ws_peer = subprocess.Popen(
                    [
                        "/usr/bin/nsenter",
                        f"--net=/proc/{peer.process.pid}/ns/net",
                        "/usr/bin/setpriv",
                        "--bounding-set=-all",
                        "--inh-caps=-all",
                        "--ambient-caps=-all",
                        "--no-new-privs",
                        "/usr/bin/python3",
                        "-I",
                        "-c",
                        WS_PEER,
                        scenario,
                        "snapshot"
                        if snapshot_ws
                        else "market"
                        if market_ws
                        else "signed"
                        if signed_ws
                        else "controls",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=ENV,
                    cwd="/",
                )
                if ws_peer.stdout.readline().strip() != "ready":
                    raise RuntimeError("ws_peer_not_ready:" + ws_peer.stderr.read()[-2000:])
                release()
            elif stage in {"ws_activated", "ws_both_live"}:
                descriptor_counts.append(len(list(Path(f"/proc/{controller.pid}/fd").iterdir())))
                if stage == "ws_both_live" and scenario == "routes_ws_controller_crash":
                    controller.kill()
                    controller.communicate(timeout=5)
                    terminal = {"status": "controller_sigkill_with_ws"}
                    time.sleep(5.1)
                    checks.append("concurrent_controller_sigkill_kernel_permission_expires")
                    break
                if stage == "ws_both_live" and scenario == "routes_ws_code_drift":
                    target = Path(entry["CODE"]) / "gateway_concurrent_ws.py"
                    original = target.read_bytes()
                    target.write_bytes(original + b"\n# fixture drift\n")
                    restore = target, original
                release()
            elif stage == "ws_native_receipt_prepared":
                revoked()
                checks.append("ws_kernel_revoked_before_native_event_delivery")
                if scenario == "routes_ws_child_stopped":
                    ws_rows = list(
                        map(
                            json.loads,
                            (
                                root
                                / (
                                    "account-market-snapshot-v1"
                                    if snapshot_ws
                                    else "account-market-ws-v1"
                                    if market_ws
                                    else "signed-account-ws-v1"
                                )
                                / "ws.jsonl"
                            )
                            .read_bytes()
                            .splitlines(),
                        )
                    )
                    signer = next(r["payload"] for r in ws_rows if r["kind"] == "signer_prepared")
                    stopped = os.pidfd_open(signer["process"]["pid"])
                    signal.pidfd_send_signal(stopped, signal.SIGSTOP)
                release()
            elif stage == "tls_headers_persisted":
                pass
            elif stage == "receipt_prepared":
                revoked()
                checks.append(f"step_{index}_kernel_revoked_before_native_receipt")
                if (
                    (index == 2 and scenario == "sequence_child_stopped")
                    or (index == 3 and scenario == "orders_child_stopped")
                    or (index == 5 and scenario == "routes_child_stopped")
                ):
                    stopped = os.pidfd_open(bindings[-1]["collector"]["process"]["pid"])
                    signal.pidfd_send_signal(stopped, signal.SIGSTOP)
                release()
            elif stage == "sequence_step_accepted":
                if message["index"] != index:
                    raise RuntimeError("sequence_acknowledgement_order")
                revoked()
                if (
                    (index == 1 and scenario == "sequence_controller_crash")
                    or (index == 2 and scenario == "orders_controller_crash")
                    or (index == 4 and scenario == "routes_controller_crash")
                ):
                    controller.kill()
                    controller.communicate(timeout=5)
                    terminal = {"status": "controller_sigkill_between_reads"}
                    checks.append("crash_between_steps_retains_consumed_sequence_without_permit")
                    break
                if (
                    (index == 0 and scenario == "sequence_code_drift")
                    or (index == 2 and scenario == "orders_code_drift")
                    or (index == 4 and scenario == "routes_code_drift")
                ):
                    target = Path(entry["CODE"]) / "gateway_read_sequence.py"
                    original = target.read_bytes()
                    target.write_bytes(original + b"\n# fixture drift\n")
                    restore = (target, original)
                release()
            elif message.get("status") in {"fixture_receipt_succeeded", "refused"}:
                finish_peer()
            elif message.get("status") in {"sequence_completed", "sequence_refused"}:
                terminal = message
                break
            else:
                raise RuntimeError("sequence_unexpected_message")
        stdout, stderr = controller.communicate(timeout=10)
        if stdout or (
            controller.returncode
            and scenario
            not in {
                "sequence_controller_crash",
                "orders_controller_crash",
                "routes_controller_crash",
                "routes_ws_controller_crash",
            }
        ):
            raise RuntimeError("sequence_controller_exit:" + stderr[-3000:])
        if stopped is not None:
            if (
                not select.select([stopped], [], [], 1)[0]
                or Path(f"/proc/{bindings[-1]['collector']['process']['pid']}").exists()
            ):
                raise RuntimeError("sequence_stopped_child_not_reaped")
            checks.append("second_account_stopped_consumer_killed_and_reaped")
        if restore is not None:
            restore[0].write_bytes(restore[1])
        revoked()
        try:
            modules["gateway"]["marked_echo"]()
        except OSError:
            checks.append("sequence_terminal_marked_socket_denied")
        else:
            raise RuntimeError("sequence_terminal_socket_allowed")
        raw = (root / "sequence.jsonl").read_bytes()
        prepared = [r for r in map(json.loads, raw.splitlines()) if r["kind"] == "prepared"]
        bundles = []
        for i in range(len(prepared)):
            directory = root / steps[i]
            scope = directory / (
                modules["ledger"].BOOKS_SCOPE
                if routes and i == 5
                else modules["ledger"].ORDERS_SCOPE
                if orders and i in {2, 3}
                else modules["ledger"].ACCOUNT_SCOPE
                if i
                else modules["ledger"].SCOPE
            )
            bundle = {}
            for key, name in code["FILES"].items():
                if key == "selection" and routes and i == 5:
                    name = "books-request.json"
                if key == "selection" and orders and i in {2, 3}:
                    name = "orders-request.json"
                path = directory / name if key == "binding" else scope / name
                if path.exists():
                    bundle[key] = path.read_text()
            bundles.append(bundle)
        report = code["replay"](
            raw,
            expected_sha256=code["digest"](raw),
            bundles=bundles,
            modules=modules,
            orders=orders,
            routes=routes,
        )
        expected = {
            **{
                name: (6, 6)
                for name in (
                    *WS_SCENARIOS,
                    *SIGNED_WS_SCENARIOS,
                    *MARKET_WS_SCENARIOS,
                    *SNAPSHOT_WS_SCENARIOS,
                )
            },
            **{
                name: (5, 5)
                if name in {"routes_controller_crash", "routes_code_drift"}
                else (6, 6)
                if name in {"routes_success", "routes_two_hops"}
                else (6, 5)
                for name in ROUTE_SCENARIOS
            },
            "orders_success": (5, 5),
            "orders_empty": (5, 5),
            "orders_changed": (4, 3),
            "orders_precision": (3, 2),
            "orders_duplicate": (3, 2),
            "orders_lock_mismatch": (3, 2),
            "orders_child_stopped": (4, 3),
            "orders_controller_crash": (3, 3),
            "orders_code_drift": (3, 3),
            "sequence_success": (3, 3),
            "sequence_metadata_mismatch": (1, 0),
            "sequence_balance_drift": (3, 2),
            "sequence_second_precision": (3, 2),
            "sequence_child_stopped": (3, 2),
            "sequence_controller_crash": (2, 2),
            "sequence_code_drift": (1, 1),
        }[scenario]
        if (
            (report["prepared_steps"], report["accepted_steps"]) != expected
            or (report["status"] == "complete")
            != (
                scenario
                in (
                    *WS_SCENARIOS,
                    *SIGNED_WS_SCENARIOS,
                    *MARKET_WS_SCENARIOS,
                    *SNAPSHOT_WS_SCENARIOS,
                )
                or scenario
                in {
                    "sequence_success",
                    "orders_success",
                    "orders_empty",
                    "routes_success",
                    "routes_two_hops",
                }
            )
            or len(peers) != expected[0]
        ):
            raise RuntimeError(
                "sequence_replay_counts:"
                + str((report["prepared_steps"], report["accepted_steps"], len(peers), terminal))
            )
        if concurrent:
            ws_code = load(payload["sources"]["gateway_concurrent_ws.py"])
            frames = load(payload["sources"]["portfolio_ws_frames.py"])
            selected = ws_code["selection"](raw, bundles, code, modules)
            extension = load(payload["sources"]["gateway_account_ws.py"]) if signed_ws else None
            state_type = (
                extension["state_type"](
                    ws_code, load(payload["sources"]["gateway_native_requests.py"])
                )
                if signed_ws
                else ws_code["State"]
            )
            if signed_ws:
                selected = extension["selection"](selected, bundles)
            market_code = load(payload["sources"]["gateway_market_ws.py"]) if market_ws else None
            if market_ws:
                selected = market_code["selection"](selected, bundles)
                state_type = market_code["state_type"](
                    ws_code, extension, load(payload["sources"]["gateway_native_requests.py"])
                )
            snapshot_code = (
                load(payload["sources"]["gateway_snapshot_ws.py"]) if snapshot_ws else None
            )
            if snapshot_ws:
                state_type = snapshot_code["state_type"](
                    ws_code,
                    extension,
                    load(payload["sources"]["gateway_native_requests.py"]),
                    market_code,
                )
            ws_scope = (
                snapshot_code["SCOPE"]
                if snapshot_ws
                else market_code["SCOPE"]
                if market_ws
                else extension["SCOPE"]
                if signed_ws
                else ws_code["SCOPE"]
            )
            ws_raw = (root / ws_scope / "ws.jsonl").read_bytes()
            ws_report = ws_code["replay"](
                ws_raw,
                expected_sha256=ws_code["digest"](ws_raw),
                selected=selected,
                provenance=modules["provenance"],
                frames=frames,
                state_type=state_type,
            )
            success = scenario in {
                "routes_ws_success",
                "routes_ws_two_hops",
                "routes_ws_overlap",
                "snapshot_success",
                "snapshot_two_hops",
            }
            if (ws_report["status"] == "complete") != success or ws_report[
                "prepared_connections"
            ] != 2:
                raise RuntimeError("ws_unexpected_result:" + json.dumps(ws_report))
            if (
                scenario != "routes_ws_controller_crash"
                and (terminal.get("concurrent_ws", {}).get("status") == "concurrent_ws_completed")
                != success
            ):
                raise RuntimeError("ws_controller_terminal_mismatch")
            ws_peer.wait(timeout=8)
            peer_report = json.loads(Path("/run/gateway-ws-peer.json").read_bytes())
            if success and (
                not peer_report["both_upgrades_before_ping"]
                or peer_report["pongs"] != 2
                or peer_report["closes"] != 2
            ):
                raise RuntimeError("ws_peer_overlap_not_verified")
            checks.extend(
                [
                    "two_ws_attempts_consumed_before_kernel_grant",
                    "ws_original_route_symbols_and_tls_controls_replay",
                    "ws_terminal_marked_socket_denied",
                    "signed_ws_partial_native_event_only"
                    if signed_ws
                    else "no_signed_ws_subscription_or_native_event_claim",
                ]
            )
            if success:
                checks.append("both_actual_ws_upgrades_coexist_before_peer_ping_and_client_close")
                if market_ws:
                    if (
                        not ws_report["market_native_acknowledged"]
                        or ws_report["market_events_recorded"] != 2 * len(selected["symbols"])
                        or peer_report.get("market_events_sent") != 2 * len(selected["symbols"])
                    ):
                        raise RuntimeError("market_ws_native_event_count")
                    checks.append(
                        "original_derived_market_increments_native_acknowledged_after_revocation"
                    )
                if snapshot_ws:
                    if (
                        ws_report["snapshot_attempts_consumed"] != len(selected["symbols"])
                        or ws_report["snapshots_accepted"] != len(selected["symbols"])
                        or sorted(peer_report["snapshot_requests"]) != selected["symbols"]
                        or not ws_report["snapshot_linked"]
                        or not ws_report["native_result"]["snapshot_linked"]
                        or ws_report["native_result"]["quote_ticks_created"]
                    ):
                        raise RuntimeError("snapshot_original_linkage_required")
                    checks.append("snapshot_originals_linked_to_per_symbol_native_delta_receipts")
            ws_result = {
                "ws_archive": ws_raw.decode(),
                "ws_replay": ws_report,
                "ws_selection": selected,
                "ws_peer": peer_report,
            }
        if max(descriptor_counts) + 64 > 1024:
            raise RuntimeError("sequence_descriptor_budget_exceeded")
        checks.append("controller_descriptors_preserve_64_spare_under_1024_without_limit_change")
        checks.append("selected_parent_and_all_child_originals_replay")
        originals = {
            str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
        }
        restarted = subprocess.run(
            command,
            input="continue\n",
            capture_output=True,
            text=True,
            env=ENV,
            cwd="/",
            timeout=10,
        )
        if (
            restarted.returncode != 1
            or restarted.stdout
            or "FileExistsError" not in restarted.stderr
            or originals
            != {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        ):
            raise RuntimeError("sequence_restart_changed_consumed_scope")
        checks.append("fresh_process_refuses_consumed_parent_and_preserves_all_originals")
        if any(name.startswith("nautilus_trader") for name in sys.modules):
            raise RuntimeError("sequence_native_loaded_by_root")
        return {
            "status": "passed",
            "scenario": scenario,
            "checks": checks,
            "base_installation": installed,
            "gateway_manifest": manifest,
            "native_runtime": native_runtime,
            "controller_descriptor_counts": descriptor_counts,
            **ws_result,
            "sequence_archive": raw.decode(),
            "bundles": bundles,
            "sequence_replay": report,
            "tls_peers": peers,
            "terminal": terminal,
            "root_native_modules_loaded": False,
        }
    finally:
        if controller.poll() is None:
            controller.kill()
            controller.communicate(timeout=3)
        if tls_peer.poll() is None:
            tls_peer.kill()
            tls_peer.communicate(timeout=3)
        if ws_peer is not None and ws_peer.poll() is None:
            ws_peer.kill()
            ws_peer.communicate(timeout=3)
        if stopped is not None:
            os.close(stopped)


def worker_ipc(payload, installed, entry, guards, module, manifest, *, native_runtime=None):
    """Shared installed fixture environment; IPC never activates a mark grant."""
    requests = payload.get("native_requests_profile", False)
    profile = module.REQUEST_PROFILE if requests else module.IPC_PROFILE
    scope_name = module.REQUEST_SCOPE if requests else module.IPC_SCOPE
    command = [
        "/usr/bin/python3",
        "-I",
        entry["CODE"] + "/installed_gateway.py",
        "--native-requests-fixture" if requests else "--joint-ipc-fixture",
    ]
    controller = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=ENV,
        cwd="/",
    )
    run, nft = guards["run"], guards["NFT"]
    checks = []
    restore = None
    try:
        line = controller.stdout.readline()
        if not line:
            raise RuntimeError("joint_ipc_controller_not_ready:" + controller.stderr.read()[-3000:])
        ready = json.loads(line)
        if ready["stage"] != "joint_ipc_ready":
            raise RuntimeError("joint_ipc_ready_required")
        identity = ready["binding"]["collector"]["process"]
        account = installed["fixture_account"]
        if (
            identity["uids"] != [account["uid"]] * 4
            or identity["gids"] != [account["gid"]] * 4
            or identity["groups"]
        ):
            raise RuntimeError("joint_ipc_distinct_uid_required")
        descriptors = [os.readlink(p) for p in Path(f"/proc/{identity['pid']}/fd").iterdir()]
        if any(
            any(
                prefix in target
                for prefix in ("/var/lib/trader", entry["CODE"], "/etc/trader", entry["CONTEXT"])
            )
            for target in descriptors
        ):
            raise RuntimeError("joint_ipc_privileged_descriptor_inherited")
        checks.extend(
            [
                "fixed_installed_sources_held",
                "dedicated_uid_pid_authenticated",
                "no_privileged_descriptor_handoff",
            ]
        )
        scope = Path(entry["STORAGE"]) / scope_name
        probe = json.loads(
            run(
                "/usr/bin/setpriv",
                f"--reuid={account['uid']}",
                f"--regid={account['gid']}",
                "--clear-groups",
                "--bounding-set=-all",
                "--inh-caps=-all",
                "--ambient-caps=-all",
                "--no-new-privs",
                "/usr/bin/python3",
                "-I",
                "-c",
                PROBE.replace("local-egress-attempts-v1", scope_name),
            )
        )
        checks.extend(probe["checks"])
        controller.stdin.write("continue\n")
        controller.stdin.flush()
        barrier = controller.stdout.readline()
        if not barrier or json.loads(barrier) != {"stage": "joint_ipc_prepared", "index": 9}:
            raise RuntimeError("joint_ipc_midpoint_missing:" + controller.stderr.read()[-3000:])
        original = (scope / "events.jsonl").read_bytes()
        midway = module.replay(
            original,
            expected_sha256=module.digest(original),
            binding_sha256=ready["binding_sha256"],
            profile=profile,
        )
        if midway["recorded_attempts"] != 10 or midway["pending_attempt"] != 9:
            raise RuntimeError("joint_ipc_unpersisted_receipt")
        checks.append("ten_operations_prepared_before_tenth_receipt")
        permits = json.loads(
            run(nft, "-j", "list", "set", "inet", "fixture_ledger_gateway", "permits")
        )
        if any(r.get("set", {}).get("elem") for r in permits["nftables"]):
            raise RuntimeError("ipc_granted_kernel_permission")
        checks.append("ipc_preparations_never_grant_kernel_permission")
        scenario = payload["scenario"]
        if scenario == "ipc_child_death":
            os.kill(identity["pid"], signal.SIGKILL)
        elif scenario == "ipc_code_drift":
            path = Path(entry["CODE"]) / (
                "gateway_native_requests.py" if requests else "gateway_joint_ipc.py"
            )
            before = path.read_bytes()
            path.write_bytes(before + b"\n# fixture drift\n")

            def restore():
                path.write_bytes(before)
        elif scenario == "ipc_account_drift":
            path = Path("/etc/group")
            before = path.read_bytes()
            path.write_bytes(before + b"foreign:x:22000:trader-egress\n")

            def restore():
                path.write_bytes(before)
        elif scenario == "ipc_storage_drift":
            path = Path(entry["STORAGE"])
            path.chmod(0o755)

            def restore():
                path.chmod(0o700)

        if scenario == "ipc_runtime_drift":
            run("/usr/bin/mount", "-o", "remount,rw,nosuid,nodev", "/run/trader-native-runtime")

            def restore():
                run("/usr/bin/mount", "-o", "remount,ro,nosuid,nodev", "/run/trader-native-runtime")

            checks.append("native_request_runtime_drift_injected")

        if scenario == "ipc_controller_crash":
            child_pidfd = os.pidfd_open(identity["pid"])
            try:
                controller.kill()
                stdout, stderr = controller.communicate(timeout=5)
                if controller.returncode != -signal.SIGKILL:
                    raise RuntimeError("joint_ipc_controller_did_not_die")
                if not select.select([child_pidfd], [], [], 2)[0]:
                    raise RuntimeError("joint_ipc_child_survived_channel_loss")
                os.waitpid(identity["pid"], 0)
                checks.append("controller_death_closes_channel_and_reaps_orphan")
            finally:
                os.close(child_pidfd)
            terminal = {"status": "controller_sigkill"}
        else:
            stdout, stderr = controller.communicate("continue\n", timeout=20)
            if controller.returncode:
                raise RuntimeError("joint_ipc_controller_failed:" + stderr[-3000:])
            terminal = json.loads(stdout)
            if terminal["status"] != (
                (
                    "native_request_custody_completed"
                    if requests
                    else "joint_ipc_accounting_completed"
                )
                if scenario == "ipc_success"
                else "refused"
            ):
                raise RuntimeError("joint_ipc_wrong_terminal")
        if restore:
            restore()
            restore = None
        raw = (scope / "events.jsonl").read_bytes()
        report = module.replay(
            raw,
            expected_sha256=module.digest(raw),
            binding_sha256=ready["binding_sha256"],
            profile=profile,
        )
        expected = 20 if scenario == "ipc_success" else 10
        if report["recorded_attempts"] != expected or report["pending_attempt"] != (
            None if expected == 20 else 9
        ):
            raise RuntimeError("joint_ipc_consumption_lost")
        if not raw.startswith(original):
            raise RuntimeError("joint_ipc_original_prefix_changed")
        checks.append("success_or_failure_keeps_original_consumption")

        # Even a root-owned marked socket must remain denied: no grant ever occurred.
        def count():
            return next(
                r["counter"]["packets"]
                for r in json.loads(
                    run(
                        nft,
                        "-j",
                        "list",
                        "counter",
                        "inet",
                        "fixture_ledger_gateway",
                        "output_denied",
                    )
                )["nftables"]
                if "counter" in r
            )

        before_count = count()
        gateway = load(payload["sources"]["ledger_gateway.py"])
        try:
            gateway["marked_echo"]()
        except OSError:
            pass
        else:
            raise RuntimeError("joint_ipc_marked_connection_allowed")
        if count() <= before_count:
            raise RuntimeError("joint_ipc_missing_kernel_denial")
        checks.append("marked_socket_denied_after_ipc_or_crash")
        restarted = subprocess.run(
            command,
            input="continue\n",
            capture_output=True,
            text=True,
            env=ENV,
            cwd="/",
            timeout=10,
        )
        if (
            restarted.returncode != 1
            or "FileExistsError" not in restarted.stderr
            or restarted.stdout
        ):
            raise RuntimeError("joint_ipc_consumed_scope_reopened")
        if (scope / "events.jsonl").read_bytes() != raw:
            raise RuntimeError("joint_ipc_restart_mutated_archive")
        checks.append("fresh_installed_process_cannot_reopen_scope")
        if (
            Path(entry["STORAGE"] + "/consumed.json").read_bytes()
            != b'{"fixture_only":true,"consumed":true}\n'
        ):
            raise RuntimeError("prior_consumed_scope_changed")
        checks.append("prior_consumed_scope_preserved")
        request_result = {}
        if requests:
            request_raw = (scope / "requests.jsonl").read_bytes()
            request_report = load(payload["sources"]["gateway_native_requests.py"])["replay"](
                request_raw,
                expected_sha256=module.digest(request_raw),
                attempts=raw,
                binding_sha256=ready["binding_sha256"],
                module=module,
            )
            if (request_report["status"] == "complete") != (scenario == "ipc_success"):
                raise RuntimeError("native_request_completion_mismatch")
            if any(name.startswith("nautilus_trader") for name in sys.modules):
                raise RuntimeError("native_package_loaded_by_root")
            request_result = {
                "request_archive": request_raw.decode(),
                "request_replay": request_report,
                "native_runtime": native_runtime,
                "root_native_modules_loaded": False,
            }
            checks.append("native_signatures_and_exact_selectors_replay_without_native_root_import")
        return {
            **request_result,
            "status": "passed",
            "scenario": scenario,
            "checks": checks,
            "base_installation": installed,
            "gateway_manifest": manifest,
            "gateway_manifest_sha256": module.digest(Path(entry["MANIFEST"]).read_bytes()),
            "binding": ready["binding"],
            "binding_sha256": ready["binding_sha256"],
            "attempt_archive": raw.decode(),
            "attempt_replay": report,
            "terminal": terminal,
            "kernel_permission_granted": False,
            "transport_dispatch_verified": False,
            "venue_requests": 0,
            "network_admitted": False,
            "trading_admitted": False,
        }
    finally:
        if restore:
            restore()
        if controller.poll() is None:
            controller.kill()
        controller.communicate(timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument("--tls-profile", action="store_true")
    profiles.add_argument("--tls-receipt-profile", action="store_true")
    profiles.add_argument("--native-receipt-profile", action="store_true")
    profiles.add_argument("--native-requests-profile", action="store_true")
    profiles.add_argument("--signed-account-profile", action="store_true")
    profiles.add_argument("--read-sequence-profile", action="store_true")
    profiles.add_argument("--order-sequence-profile", action="store_true")
    profiles.add_argument("--route-sequence-profile", action="store_true")
    profiles.add_argument("--concurrent-ws-profile", action="store_true")
    profiles.add_argument("--signed-ws-profile", action="store_true")
    profiles.add_argument("--market-ws-profile", action="store_true")
    profiles.add_argument("--snapshot-ws-profile", action="store_true")
    profiles.add_argument("--joint-ipc-profile", action="store_true")
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        parser.error("run the disposable wrapper as an ordinary user")
    fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        directory = Path(__file__).resolve().parent
        base_source = (directory / "installation_selftest.py").read_text()
        base = load(base_source)
        installer = (directory / "package.py").read_bytes()
        if base["sha"](installer) != base["INSTALLER_PIN"]:
            raise ValueError("reviewed_installer_changed")
        package = load(installer)
        package["build"].__globals__["__file__"] = str(directory / "package.py")
        bundle = package["build"]()
        package["inspect"](bundle, base["PIN"])
        entry = load((directory / "installed_gateway.py").read_bytes())
        sources = {
            name: (
                (
                    directory.parents[1] / "apps/strategies_nautilus"
                    if name.startswith("portfolio_")
                    else directory
                )
                / name
            ).read_text()
            for name in entry["FILES"]
        }
        native_bundle = None
        if (
            args.native_receipt_profile
            or args.native_requests_profile
            or args.signed_account_profile
            or args.read_sequence_profile
            or args.order_sequence_profile
            or args.route_sequence_profile
            or args.concurrent_ws_profile
            or args.signed_ws_profile
            or args.market_ws_profile
            or args.snapshot_ws_profile
        ):
            built = subprocess.run(
                [
                    str(directory.parents[1] / ".venv/bin/python"),
                    "-I",
                    str(directory / "gateway_native_runtime.py"),
                ],
                capture_output=True,
                check=True,
                timeout=60,
                env=ENV,
            )
            native_bundle = base64.b64decode(built.stdout.strip(), validate=True)
            with args.report.with_suffix(".runtime.tar.gz").open("xb") as runtime_output:
                runtime_output.write(native_bundle)
                runtime_output.flush()
                os.fsync(runtime_output.fileno())
        payload = {
            **(
                {
                    "native_bundle": base64.b64encode(native_bundle).decode(),
                    "native_bundle_sha256": base["sha"](native_bundle),
                }
                if native_bundle is not None
                else {}
            ),
            "source": Path(__file__).read_text(),
            "tls_profile": args.tls_profile,
            "tls_receipt_profile": args.tls_receipt_profile,
            "native_receipt_profile": args.native_receipt_profile,
            "native_requests_profile": args.native_requests_profile,
            "signed_account_profile": args.signed_account_profile,
            "read_sequence_profile": args.read_sequence_profile,
            "order_sequence_profile": args.order_sequence_profile,
            "route_sequence_profile": args.route_sequence_profile,
            "concurrent_ws_profile": args.concurrent_ws_profile,
            "signed_ws_profile": args.signed_ws_profile,
            "market_ws_profile": args.market_ws_profile,
            "snapshot_ws_profile": args.snapshot_ws_profile,
            "joint_ipc_profile": args.joint_ipc_profile,
            "base_source": base_source,
            "installer": installer.decode(),
            "bundle": base64.b64encode(bundle).decode(),
            "original": base["namespaces"](),
            "sources": sources,
            "source_sha256": {name: base["sha"](raw.encode()) for name, raw in sources.items()},
        }
        before = base["host_observation"]()
        reports = []
        bootstrap = "import json,sys\np=json.load(sys.stdin)\ns={'__name__':'isolated_installed_gateway'}\nexec(compile(p['source'],'<fixture>','exec'),s)\nprint(json.dumps(s['worker'](p),sort_keys=True))\n"
        for scenario in (
            SNAPSHOT_WS_SCENARIOS
            if args.snapshot_ws_profile
            else MARKET_WS_SCENARIOS
            if args.market_ws_profile
            else SIGNED_WS_SCENARIOS
            if args.signed_ws_profile
            else WS_SCENARIOS
            if args.concurrent_ws_profile
            else ROUTE_SCENARIOS
            if args.route_sequence_profile
            else ORDER_SCENARIOS
            if args.order_sequence_profile
            else SEQUENCE_SCENARIOS
            if args.read_sequence_profile
            else REQUEST_SCENARIOS
            if args.native_requests_profile
            else IPC_SCENARIOS
            if args.joint_ipc_profile
            else NATIVE_SCENARIOS
            if args.native_receipt_profile or args.signed_account_profile
            else RECEIPT_SCENARIOS
            if args.tls_receipt_profile
            else TLS_SCENARIOS
            if args.tls_profile
            else SCENARIOS
        ):
            command = [
                "/usr/bin/sudo",
                "-n",
                "/usr/bin/unshare",
                "--mount",
                "--net",
                "--pid",
                "--fork",
                "--kill-child",
                "--mount-proc",
                "--propagation",
                "private",
                "/usr/bin/python3",
                "-I",
                "-c",
                bootstrap,
            ]
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=ENV,
                cwd="/",
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(
                    json.dumps({**payload, "scenario": scenario}), timeout=70
                )
            except BaseException:
                subprocess.run(
                    ["/usr/bin/sudo", "-n", "/usr/bin/kill", "-KILL", "--", f"-{process.pid}"],
                    capture_output=True,
                    env=ENV,
                    timeout=5,
                    check=False,
                )
                process.communicate(timeout=5)
                raise
            if base["namespaces"]() != payload["original"] or base["host_observation"]() != before:
                raise RuntimeError("host_observation_changed")
            if process.returncode:
                raise RuntimeError(scenario + ":" + stderr[-5000:])
            report = json.loads(stdout)
            if report["status"] != "passed" or report["scenario"] != scenario:
                raise RuntimeError("invalid_installed_gateway_report")
            reports.append(report)
        result = {
            "schema_version": "portfolio.installed_gateway_acceptance.v1",
            **(
                {"native_bundle_sha256": base["sha"](native_bundle)}
                if native_bundle is not None
                else {}
            ),
            "status": "passed",
            "tls_profile": args.tls_profile,
            "tls_receipt_profile": args.tls_receipt_profile,
            "native_receipt_profile": args.native_receipt_profile,
            "native_requests_profile": args.native_requests_profile,
            "signed_account_profile": args.signed_account_profile,
            "read_sequence_profile": args.read_sequence_profile,
            "order_sequence_profile": args.order_sequence_profile,
            "route_sequence_profile": args.route_sequence_profile,
            "concurrent_ws_profile": args.concurrent_ws_profile,
            "signed_ws_profile": args.signed_ws_profile,
            "market_ws_profile": args.market_ws_profile,
            "snapshot_ws_profile": args.snapshot_ws_profile,
            "joint_ipc_profile": args.joint_ipc_profile,
            "scenarios": reports,
            "source_sha256": payload["source_sha256"],
            "harness_sha256": base["sha"](payload["source"].encode()),
            "base_harness_sha256": base["sha"](base_source.encode()),
            "bundle_sha256": base["PIN"],
            "host_observations_unchanged": True,
            "host_before_after": before,
            "host_installation_performed": False,
            "venue_requests": 0,
            "power_loss_qualified": False,
            "complete_caller_coverage_verified": False,
            "network_admitted": False,
            "trading_admitted": False,
        }
        raw = (json.dumps(result, sort_keys=True, indent=2) + "\n").encode()
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    print(
        json.dumps(
            {
                "status": "passed",
                "scenarios": len(reports),
                "checks_per_scenario": [len(row["checks"]) for row in reports],
                "report_sha256": base["sha"](raw),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
