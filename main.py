from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.route import exam_router, admin_router
from config.database import SessionLocal, engine
import uvicorn
from models import models

models.Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="ChronosAssessment: Scheduled CBT Platform API",
    description="Backend API for secure, time-bound, class-specific computer-based testing.",
    version="1.0.0",
)

origins = [
    "http://localhost",
    "https://fastquiz-skmb.onrender.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    exam_router, 
    tags=["Student Exam Flow (Public)"]
)

app.include_router(
    admin_router, 
    tags=["Admin Management (Secured)"]
)

@app.get("/", include_in_schema=False)
def read_root():
    return {"message": "Welcome to CronosAssessment API. Access documentation at /docs."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)