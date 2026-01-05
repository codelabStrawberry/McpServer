# api/routes/docs.py
from fastapi import APIRouter
from api.schemas import DocPayload
from chroma_db import add_doc, add_document

router = APIRouter()

@router.post("/add_doc")
async def add_doc_api(payload: DocPayload):
    await add_doc(payload.id, payload.text)
    return {"status": "ok"}

@router.post("/add_doc2")
async def add_doc2_api(payload: DocPayload):
    await add_document(payload.id, payload.text)
    return {"status": "ok"}
