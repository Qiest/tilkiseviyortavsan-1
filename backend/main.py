import os
import io
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from bson import ObjectId
import uvicorn

# ── Config ────────────────────────────────────────────────────────────────────
MONGO_URL       = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME         = "sapsalTavsan"
USER_PASSWORD   = "280126"
ADMIN_PASSWORD  = "ec280126"
ANNIVERSARY     = datetime(2026, 1, 28, 0, 0, 0, tzinfo=timezone.utc)

# ── App & CORS ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Şapşal Tavşan API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Tüm dünyadan (Netlify dahil) gelen isteklere izin ver!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB Helpers ─────────────────────────────────────────────────────────────────
client: Optional[AsyncIOMotorClient] = None
db     = None
fs     = None

@app.on_event("startup")
async def startup():
    global client, db, fs
    client = AsyncIOMotorClient(MONGO_URL)
    db     = client[DB_NAME]
    fs     = AsyncIOMotorGridFSBucket(db)
    # Ensure index
    await db.memories.create_index([("date", -1)])

@app.on_event("shutdown")
async def shutdown():
    if client:
        client.close()

# ── Auth ───────────────────────────────────────────────────────────────────────
@app.post("/api/auth/login")
async def login(request: Request):
    body = await request.json()
    password = body.get("password", "")
    if password == ADMIN_PASSWORD:
        return {"role": "admin", "ok": True}
    if password == USER_PASSWORD:
        return {"role": "user",  "ok": True}
    raise HTTPException(status_code=401, detail="Wrong password 💔")

# ── Anniversary Counter ────────────────────────────────────────────────────────
@app.get("/api/anniversary")
async def anniversary():
    now   = datetime.now(timezone.utc)
    delta = now - ANNIVERSARY
    total_seconds = int(delta.total_seconds())
    days    = delta.days
    hours   = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600)  // 60
    seconds = total_seconds % 60
    return {"days": days, "hours": hours, "minutes": minutes, "seconds": seconds}

# ── Memories ───────────────────────────────────────────────────────────────────
@app.get("/api/memories")
async def list_memories():
    cursor = db.memories.find().sort("date", -1)
    memories = []
    async for doc in cursor:
        memories.append({
            "id":       str(doc["_id"]),
            "caption":  doc.get("caption", ""),
            "date":     doc.get("date", ""),
            "fileId":   str(doc.get("fileId", "")),
            "fileType": doc.get("fileType", "image"),
        })
    return memories

@app.post("/api/memories")
async def create_memory(
    file:    UploadFile = File(...),
    caption: str        = Form(""),
    date:    str        = Form(""),
):
    content   = await file.read()
    file_type = "video" if file.content_type and "video" in file.content_type else "image"

    # Store file in GridFS
    file_id = await fs.upload_from_stream(
        file.filename,
        io.BytesIO(content),
        metadata={"contentType": file.content_type},
    )

    doc = {
        "caption":  caption,
        "date":     date or datetime.now(timezone.utc).isoformat(),
        "fileId":   file_id,
        "fileType": file_type,
        "createdAt": datetime.now(timezone.utc),
    }
    result = await db.memories.insert_one(doc)
    return {"id": str(result.inserted_id), "ok": True}

@app.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: str):
    doc = await db.memories.find_one({"_id": ObjectId(memory_id)})
    if not doc:
        raise HTTPException(404, "Memory not found")
    # Delete GridFS file
    try:
        await fs.delete(doc["fileId"])
    except Exception:
        pass
    await db.memories.delete_one({"_id": ObjectId(memory_id)})
    return {"ok": True}

# ── Media Streaming ────────────────────────────────────────────────────────────
@app.get("/api/media/{file_id}")
async def stream_media(file_id: str, request: Request):
    try:
        oid = ObjectId(file_id)
    except Exception:
        raise HTTPException(400, "Invalid file id")

    # Find file metadata
    file_doc = await db["fs.files"].find_one({"_id": oid})
    if not file_doc:
        raise HTTPException(404, "File not found")

    content_type = (file_doc.get("metadata") or {}).get("contentType", "application/octet-stream")
    file_length  = file_doc["length"]

    # Range support for video streaming
    range_header = request.headers.get("range")
    if range_header and "video" in content_type:
        range_val   = range_header.strip().replace("bytes=", "")
        start_str, _, end_str = range_val.partition("-")
        start = int(start_str) if start_str else 0
        end   = int(end_str)   if end_str   else file_length - 1
        end   = min(end, file_length - 1)
        chunk_size = end - start + 1

        async def range_generator():
            stream = await fs.open_download_stream(oid)
            # skip to start
            skipped = 0
            async for chunk in stream:
                if skipped + len(chunk) <= start:
                    skipped += len(chunk)
                    continue
                offset = max(0, start - skipped)
                data   = chunk[offset:]
                skipped += len(chunk)
                if len(data) > chunk_size:
                    yield data[:chunk_size]
                    break
                chunk_size -= len(data)
                yield data
                if chunk_size <= 0:
                    break

        return StreamingResponse(
            range_generator(),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range":  f"bytes {start}-{end}/{file_length}",
                "Accept-Ranges":  "bytes",
                "Content-Length": str(end - start + 1),
            },
        )

    # Full stream
    async def full_generator():
        stream = await fs.open_download_stream(oid)
        async for chunk in stream:
            yield chunk

    return StreamingResponse(
        full_generator(),
        media_type=content_type,
        headers={
            "Accept-Ranges":  "bytes",
            "Content-Length": str(file_length),
        },
    )

# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
