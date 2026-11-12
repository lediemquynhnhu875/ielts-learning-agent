"""Network-free OpenAI-compatible HTTP harness shared by agent tests."""

import json

import httpx
from openai import OpenAI


class WireHarness:
    def __init__(self, *, content=None, finish_reason="stop", status=200):
        self.content = content
        self.finish_reason = finish_reason
        self.status = status
        self.requests = []
        self.client = OpenAI(
            api_key="offline-test-key",
            base_url="https://offline.invalid/v1",
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(self.handle)),
        )

    def handle(self, request):
        self.requests.append({"url": str(request.url), "body": json.loads(request.content)})
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {
                "message": "RAW_UPSTREAM_SECRET", "type": "invalid_request_error",
            }})
        content = json.dumps(self.content) if isinstance(self.content, dict) else self.content
        return httpx.Response(200, json={
            "id": "offline-completion", "object": "chat.completion",
            "created": 0, "model": "offline-model",
            "choices": [{"index": 0, "finish_reason": self.finish_reason,
                         "message": {"role": "assistant", "content": content}}],
        })

    def close(self):
        self.client.close()
