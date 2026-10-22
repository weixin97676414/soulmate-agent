




import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


@dataclass
class MockRoute:

    method: str = "GET"
    path: str = "/"
    response_body: Any = None
    response_status: int = 200
    response_headers: Dict[str, str] = field(default_factory=dict)
    delay: float = 0.0
    callback: Optional[Callable] = None
    
    def method(self, http_method: str):

        self.method = http_method.upper()
        return self
    
    def path(self, path_pattern: str):

        self.path = path_pattern
        return self
    
    def response(self, status: int, body: Any = None, headers: Optional[Dict] = None):

        self.response_status = status
        self.response_body = body
        if headers:
            self.response_headers.update(headers)
        return self
    
    def delay(self, seconds: float):

        self.delay = seconds
        return self
    
    def match(self, method: str, path: str) -> bool:

        if self.method != method.upper():
            return False
        
        pattern = self.path.replace("*", ".*")
        return bool(re.match(pattern, path))


class MockServer:

    
    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.host = host
        self.port = port
        self.routes: List[MockRoute] = []
        self.request_log: List[Dict] = []
        self.server: Optional[uvicorn.Server] = None
        self.app = self._create_app()
        
    def _create_app(self) -> Starlette:

        return Starlette(
            routes=[
                Route("/{path:path}", self._handle_request, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]),
            ]
        )
    
    async def _handle_request(self, request: Request):

        method = request.method
        path = request.url.path
        
        
        body = await request.body()
        self.request_log.append({
            "method": method,
            "path": path,
            "headers": dict(request.headers),
            "body": body.decode() if body else None,
            "query_params": dict(request.query_params),
        })
        
        
        for route in self.routes:
            if route.match(method, path):
                
                if route.delay > 0:
                    await asyncio.sleep(route.delay)
                
                
                if route.callback:
                    response_body = route.callback(request)
                else:
                    response_body = route.response_body
                
                return JSONResponse(
                    content=response_body,
                    status_code=route.response_status,
                    headers=route.response_headers
                )
        
        
        return JSONResponse(
            content={"error": "Not Found"},
            status_code=404
        )
    
    def add_route(self, route: MockRoute):

        self.routes.append(route)
    
    def add_json_endpoint(self, path: str, data: Any, method: str = "GET", status: int = 200):

        self.add_route(
            MockRoute()
            .method(method)
            .path(path)
            .response(status, data)
        )
    
    def start(self):

        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info")
        self.server = uvicorn.Server(config)
        
        
        import threading
        self.thread = threading.Thread(target=self.server.run)
        self.thread.daemon = True
        self.thread.start()
        print(f"Mock server started at http://{self.host}:{self.port}")
    
    def stop(self):

        if self.server:
            self.server.should_exit = True
            print("Mock server stopped")
    
    def clear_log(self):

        self.request_log.clear()
    
    def get_request_log(self) -> List[Dict]:

        return self.request_log.copy()
    
    def was_called(self, path: Optional[str] = None, method: Optional[str] = None) -> bool:

        for log in self.request_log:
            if path and log["path"] != path:
                continue
            if method and log["method"] != method.upper():
                continue
            return True
        return False
    
    def get_call_count(self, path: Optional[str] = None, method: Optional[str] = None) -> int:

        count = 0
        for log in self.request_log:
            if path and log["path"] != path:
                continue
            if method and log["method"] != method.upper():
                continue
            count += 1
        return count


class MockBuilder:

    
    def __init__(self):
        self.server = MockServer()
    
    def with_endpoint(self, path: str, response: Any, method: str = "GET", status: int = 200) -> "MockBuilder":

        self.server.add_json_endpoint(path, response, method, status)
        return self
    
    def with_delay(self, delay: float) -> "MockBuilder":

        
        return self
    
    def on_port(self, port: int) -> "MockBuilder":

        self.server.port = port
        return self
    
    def build(self) -> MockServer:

        return self.server
