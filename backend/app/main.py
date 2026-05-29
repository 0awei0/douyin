from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.analyze import router as analyze_router

app = FastAPI(title="爆款结构迁移引擎", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
