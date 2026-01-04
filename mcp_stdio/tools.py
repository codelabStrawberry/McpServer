# mcp_stdio/tools.py

TOOLS = {
    "chat": {
        "name": "chat",
        "description": "LLM 단독 채팅 (Ollama)",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"}
            },
            "required": ["prompt"]
        }
    },
    "rag_chat": {
        "name": "rag_chat",
        "description": "RAG 기반 질의 응답",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"}
            },
            "required": ["question"]
        }
    },
    "add_doc": {
        "name": "add_doc",
        "description": "RAG 문서 추가 (add_doc)",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "text": {"type": "string"}
            },
            "required": ["id", "text"]
        }
    },
    "add_doc2": {
        "name": "add_doc2",
        "description": "RAG 문서 추가 (add_document)",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "text": {"type": "string"}
            },
            "required": ["id", "text"]
        }
    }
}
