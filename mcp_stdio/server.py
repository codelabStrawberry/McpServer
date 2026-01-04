# mcp_stdio/server.py
import sys
import json

from tools import TOOLS
from client import chat, rag_chat, add_doc, add_doc2


def send_result(id_, result):
    print(json.dumps({
        "jsonrpc": "2.0",
        "id": id_,
        "result": result
    }), flush=True)


def send_error(id_, message):
    print(json.dumps({
        "jsonrpc": "2.0",
        "id": id_,
        "error": {
            "code": -32000,
            "message": message
        }
    }), flush=True)


def handle(req: dict):
    method = req.get("method")

    # ---------------------------
    # MCP handshake
    # ---------------------------
    if method == "initialize":
        return {
            "protocolVersion": "2025-06-18",
            "serverInfo": {
                "name": "ollama-rag-mcp",
                "version": "0.1.0"
            },
            "capabilities": {
                "tools": {}
            }
        }

    # ---------------------------
    # Notifications (no response needed)
    # ---------------------------
    if method == "notifications/initialized":
        # Notification이므로 응답하지 않음
        return None
    
    if method and method.startswith("notifications/"):
        # 다른 notification들도 무시
        return None

    # ---------------------------
    # Tool list
    # ---------------------------
    if method == "tools/list":
        return {
            "tools": list(TOOLS.values())
        }

    # ---------------------------
    # Tool call
    # ---------------------------
    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})

        if name == "chat":
            return chat(args.get("prompt"))

        if name == "rag_chat":
            return rag_chat(args.get("question"))

        if name == "add_doc":
            return add_doc(args.get("id"), args.get("text"))

        if name == "add_doc2":
            return add_doc2(args.get("id"), args.get("text"))

        raise ValueError(f"Unknown tool: {name}")

    raise ValueError(f"Unknown method: {method}")


def main():
    print("[SERVER] Starting MCP server...", file=sys.stderr, flush=True)
    
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue  # 빈 줄 무시

            req = None
            try:
                req = json.loads(line)
                method = req.get("method", "unknown")
                print(f"[SERVER] Received: {method}", file=sys.stderr, flush=True)
                
                result = handle(req)
                
                # Notification (id가 없는 메시지)은 응답하지 않음
                if result is not None and req.get("id") is not None:
                    send_result(req.get("id"), result)
                    print(f"[SERVER] Sent response for {method}", file=sys.stderr, flush=True)
                elif result is None:
                    print(f"[SERVER] Skipped response for notification: {method}", file=sys.stderr, flush=True)

            except Exception as e:
                print(f"[SERVER] Error processing request: {e}", file=sys.stderr, flush=True)
                if not isinstance(req, dict):
                    continue
                req_id = req.get("id")
                # Notification 오류는 무시 (id가 None)
                if req_id is not None:
                    send_error(req_id, str(e))
                    
    except KeyboardInterrupt:
        print("[SERVER] Shutting down gracefully...", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[SERVER] Fatal error: {e}", file=sys.stderr, flush=True)
        raise


if __name__ == "__main__":
    main()