import os
import uuid
import shutil
from typing import List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

TEMP_DIR = "/tmp/processed_files"
os.makedirs(TEMP_DIR, exist_ok=True)

app = FastAPI(title="PDF Tools API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "PDF Tools Backend is running"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Simple health check"""
    return {"backend": "✅ Running"}


def _save_upload(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a filename")
    filename = os.path.basename(file.filename)
    ext = filename.split(".")[-1].lower()
    safe_id = str(uuid.uuid4())
    dest_path = os.path.join(TEMP_DIR, f"{safe_id}.{ext}")
    with open(dest_path, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return dest_path


def _make_download(file_path: str, label: str) -> JSONResponse:
    file_id = os.path.basename(file_path)
    return JSONResponse({
        "file_id": file_id,
        "filename": label,
        "download_url": f"/api/download/{file_id}"
    })


@app.post("/api/pdf/merge")
async def merge_pdfs(files: List[UploadFile] = File(...)):
    try:
        from PyPDF2 import PdfReader, PdfWriter
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF engine unavailable: {e}")

    if not files or len(files) < 2:
        raise HTTPException(status_code=400, detail="Please upload at least two PDF files to merge")

    writer = PdfWriter()
    saved_paths = []
    try:
        for f in files:
            if not f.filename.lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail=f"{f.filename} is not a PDF")
            p = _save_upload(f)
            saved_paths.append(p)
            reader = PdfReader(p)
            for page in reader.pages:
                writer.add_page(page)
        out_id = str(uuid.uuid4())
        out_path = os.path.join(TEMP_DIR, f"merged_{out_id}.pdf")
        with open(out_path, "wb") as out_file:
            writer.write(out_file)
        return _make_download(out_path, f"merged_{out_id}.pdf")
    finally:
        for p in saved_paths:
            try:
                os.remove(p)
            except Exception:
                pass


@app.post("/api/pdf/split")
async def split_pdf(file: UploadFile = File(...), start_page: int = Form(...), end_page: int = Form(...)):
    try:
        from PyPDF2 import PdfReader, PdfWriter
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF engine unavailable: {e}")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a PDF")
    src_path = _save_upload(file)
    try:
        reader = PdfReader(src_path)
        total = len(reader.pages)
        if start_page < 1 or end_page < start_page or end_page > total:
            raise HTTPException(status_code=400, detail=f"Invalid page range. Document has {total} pages.")
        writer = PdfWriter()
        for i in range(start_page - 1, end_page):
            writer.add_page(reader.pages[i])
        out_id = str(uuid.uuid4())
        out_path = os.path.join(TEMP_DIR, f"split_{out_id}.pdf")
        with open(out_path, "wb") as out_file:
            writer.write(out_file)
        return _make_download(out_path, f"split_{out_id}.pdf")
    finally:
        try:
            os.remove(src_path)
        except Exception:
            pass


@app.post("/api/pdf/images-to-pdf")
async def images_to_pdf(images: List[UploadFile] = File(...)):
    try:
        from PIL import Image
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image engine unavailable: {e}")

    if not images:
        raise HTTPException(status_code=400, detail="Please upload at least one image")

    saved_paths = []
    pil_images = []
    try:
        for img in images:
            if not any(img.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]):
                raise HTTPException(status_code=400, detail=f"Unsupported image format: {img.filename}")
            p = _save_upload(img)
            saved_paths.append(p)
            pil = Image.open(p).convert("RGB")
            pil_images.append(pil)
        out_id = str(uuid.uuid4())
        out_path = os.path.join(TEMP_DIR, f"images_{out_id}.pdf")
        first, rest = pil_images[0], pil_images[1:]
        first.save(out_path, save_all=True, append_images=rest, format="PDF")
        return _make_download(out_path, f"images_{out_id}.pdf")
    finally:
        for p in saved_paths:
            try:
                os.remove(p)
            except Exception:
                pass
        for im in pil_images:
            try:
                im.close()
            except Exception:
                pass


@app.get("/api/download/{file_id}")
async def download_file(file_id: str):
    safe_name = os.path.basename(file_id)
    file_path = os.path.join(TEMP_DIR, safe_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found or expired")
    return FileResponse(path=file_path, filename=safe_name, media_type="application/pdf")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
