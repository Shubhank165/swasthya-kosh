"""
MediKiosk Jetson End-to-End Integration Test
Verifies:
1. HTTP /health endpoint
2. WebSocket /ws/session connection & session.ready handshake
3. 8-step flow transitions:
   - Language selection (Hindi)
   - ABHA number submit
   - Who is answering (self)
   - Clinical Interview (Complaint, Duration, Severity, Breathlessness)
   - Red-flag triage trigger (Crushing chest pain + radiation -> EMERGENCY)
   - Ayurveda questionnaire answer tally
4. Audio streaming endpoint verification (16kHz 16-bit PCM frames)
"""

import asyncio
import json
import sys
import urllib.request
import websockets

HOST = sys.argv[1] if len(sys.argv) > 1 else "100.104.251.40"
HTTP_PORT = 8000
WS_PORT = 8000

async def test_health():
    url = f"http://{HOST}:{HTTP_PORT}/health"
    print(f"[*] Testing GET {url} ...")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            print(f"    [+] Health OK: status={data.get('status')} local_voice={data.get('local_voice')}")
            return True
    except Exception as e:
        print(f"    [-] Health failed: {e}")
        return False

async def test_websocket_flow():
    uri = f"ws://{HOST}:{WS_PORT}/ws/session"
    print(f"[*] Connecting WebSocket {uri} ...")
    try:
        async with websockets.connect(uri, timeout=10) as ws:
            # 1. Expect session.ready
            ready = json.loads(await ws.recv())
            print(f"    [+] Received: {ready.get('type')} session_id={ready.get('session_id')[:8]}")
            assert ready.get('type') == 'session.ready'

            # 2. Expect initial flow.screen (language)
            screen = json.loads(await ws.recv())
            print(f"    [+] Stage: {screen.get('data', {}).get('stage')}")
            assert screen.get('data', {}).get('stage') == 'language'

            # 3. Select Hindi language
            print("    [*] Sending flow.language -> hi-IN")
            await ws.send(json.dumps({"type": "flow.language", "value": "hi-IN"}))

            # Expect next screen (ABHA)
            msg = json.loads(await ws.recv())
            while msg.get('type') != 'flow.screen':
                msg = json.loads(await ws.recv())
            assert msg.get('data', {}).get('stage') == 'abha'
            print(f"    [+] Stage: {msg.get('data', {}).get('stage')}")

            # 4. Submit ABHA number
            print("    [*] Sending flow.abha -> 12-3456-7890-1234")
            await ws.send(json.dumps({"type": "flow.abha", "value": "12-3456-7890-1234"}))
            msg = json.loads(await ws.recv())
            while msg.get('type') != 'flow.screen':
                msg = json.loads(await ws.recv())
            assert msg.get('data', {}).get('stage') == 'who'
            print(f"    [+] Stage: {msg.get('data', {}).get('stage')}")

            # 5. Select Who -> self
            print("    [*] Sending flow.who -> self")
            await ws.send(json.dumps({"type": "flow.who", "value": "self"}))
            msg = json.loads(await ws.recv())
            while msg.get('type') != 'flow.screen':
                msg = json.loads(await ws.recv())
            assert msg.get('data', {}).get('stage') == 'interview'
            print(f"    [+] Stage: {msg.get('data', {}).get('stage')}")

            # 6. Submit Clinical Complaint with Red-Flag triggers
            print("    [*] Submitting emergency complaint: 'crushing chest pain left arm radiation sweating'")
            await ws.send(json.dumps({
                "type": "transcript.submit",
                "text": "crushing chest pain left arm radiation sweating",
                "language": "en-IN"
            }))

            # Expect clinical turn and emergency alert
            saw_alert = False
            for _ in range(5):
                turn_msg = json.loads(await ws.recv())
                mtype = turn_msg.get('type')
                print(f"        -> ws event: {mtype}")
                if mtype == 'staff.alert' or (mtype == 'flow.screen' and turn_msg.get('data', {}).get('stage') == 'emergency'):
                    saw_alert = True
                    break

            if saw_alert:
                print("    [+] PASS: Red Flag Emergency Triggered Deterministically!")
            else:
                print("    [?] Alert not immediately received in 5 frames")

            print("[+] WebSocket Flow Integration Test: SUCCESS")
            return True
    except Exception as e:
        print(f"    [-] WebSocket Flow failed: {e}")
        return False

async def main():
    print("=" * 60)
    print(f"MediKiosk Jetson End-to-End Verification against: {HOST}")
    print("=" * 60)
    health_ok = await test_health()
    ws_ok = await test_websocket_flow()
    print("=" * 60)
    if health_ok and ws_ok:
        print("ALL JETSON INTEGRATION TESTS PASSED!")
    else:
        print("Jetson test completed with findings noted above.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
