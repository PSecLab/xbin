import os
import uuid
import time
import grpc
import json
import redis
import requests
import threading
import signal
import sys
from dataclasses import dataclass
from typing import Callable, Optional, Dict, Any

# Import the generated gRPC bits
try:
    from xbin_orchestrator import orchestrator_pb2
    from xbin_orchestrator import orchestrator_pb2_grpc
except (ImportError, ValueError):
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "xbin_orchestrator"))
    import orchestrator_pb2
    import orchestrator_pb2_grpc

@dataclass
class Match:
    symbol: str
    confidence: float

@dataclass
class TaskContext:
    address: int
    raw_bytes: bytes

class Worker:
    def __init__(self, name: str, category: str, version: str):
        self.name = name
        self.category = category
        self.version = version
        self.worker_id = f"{name}-{uuid.uuid4().hex[:8]}"
        
        self.on_binary_handler: Optional[Callable[[str], None]] = None
        self.on_update_handler: Optional[Callable[[str, str, Dict[str, Any]], None]] = None
        
        self.orchestrator_addr = os.getenv("XBIN_ORCHESTRATOR", "localhost:50051")
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.rest_url = f"http://{self.orchestrator_addr.split(':')[0]}:8000"
        
        self._channel = grpc.insecure_channel(self.orchestrator_addr)
        self._stub = orchestrator_pb2_grpc.OrchestratorServiceStub(self._channel)
        self._redis = redis.Redis(host=self.redis_host, port=6379, decode_responses=True)
        self._is_running = True
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_exit)
        signal.signal(signal.SIGINT, self._handle_exit)

    def _handle_exit(self, signum, frame):
        print(f"[*] Received shutdown signal ({signum}). Sending goodbye...")
        self._is_running = False
        try:
            self._stub.Heartbeat(orchestrator_pb2.HeartbeatRequest(
                worker_id=self.worker_id,
                status_message="SHUTDOWN"
            ))
        except: pass
        sys.exit(0)

    def _heartbeat_loop(self):
        """Persistent background loop to send vitality signals."""
        print(f"[*] Heartbeat loop started for {self.worker_id}")
        while self._is_running:
            try:
                self._stub.Heartbeat(orchestrator_pb2.HeartbeatRequest(
                    worker_id=self.worker_id,
                    status_message="Online & Ready"
                ))
            except Exception as e:
                print(f"[!] Heartbeat failed: {e}")
            time.sleep(5)

    def register(self):
        print(f"========================================")
        print(f"   XBIN ADAPTER: {self.name.upper()}     ")
        print(f"   ID: {self.worker_id}                 ")
        print(f"========================================")
        print(f"[*] Connecting to orchestrator at {self.orchestrator_addr}...")
        
        try:
            resp = self._stub.RegisterWorker(orchestrator_pb2.RegisterRequest(
                worker_id=self.worker_id, 
                backend_name=self.name,
                analysis_type=self.category
            ))
            if resp.success:
                print(f"[+] Welcome signal acknowledged. I am READY.")
                threading.Thread(target=self._heartbeat_loop, daemon=True).start()
                return True
        except Exception as e:
            print(f"[-] Registration failed: {e}")
            return False

    def post_result(self, item_key: str, data: Any, confidence: float):
        try:
            self._stub.PostResult(orchestrator_pb2.PostResultRequest(
                analysis_type=self.category,
                item_key=item_key,
                result_data=json.dumps(data),
                confidence=confidence,
                backend_name=self.name
            ))
        except Exception as e:
            print(f"[-] Failed to post result for {item_key}: {e}")

    def get_analysis(self, category: str, item_key: Optional[str] = None):
        url = f"{self.rest_url}/api/v1/blackboard/{category}"
        if item_key: url += f"/{item_key}"
        try:
            resp = requests.get(url)
            return resp.json()
        except Exception as e:
            print(f"[-] Failed to get analysis {category}: {e}")
            return None

    def run(self):
        if not self.register(): 
            print("[-] Critical Failure: Could not join the xbin network.")
            return
        
        print(f"[*] {self.name} listening for blackboard events...")
        pubsub = self._redis.pubsub()
        pubsub.subscribe("xbin:events")
        
        try:
            for message in pubsub.listen():
                if message["type"] == "message":
                    event = json.loads(message["data"])
                    if event["type"] == "NEW_BINARY" and self.on_binary_handler:
                        self.on_binary_handler(event["path"])
                    elif event["type"] == "BLACKBOARD_UPDATE" and self.on_update_handler:
                        self.on_update_handler(event["analysis_type"], event["item_key"], event["top_hypothesis"])
        except KeyboardInterrupt:
            self._is_running = False
            print("[*] Worker exiting.")

_current_worker: Optional[Worker] = None

def plugin(name: str, category: str, version: str = "1.0"):
    global _current_worker
    _current_worker = Worker(name, category, version)
    def decorator(cls):
        instance = cls()
        if hasattr(instance, 'on_new_binary'):
            _current_worker.on_binary_handler = instance.on_new_binary
        if hasattr(instance, 'on_update'):
            _current_worker.on_update_handler = instance.on_update
        return cls
    return decorator

def start_worker():
    if _current_worker:
        _current_worker.run()
    else:
        print("[-] No plugin defined.")
