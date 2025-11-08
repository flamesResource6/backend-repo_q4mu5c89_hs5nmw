import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Task, TaskOut

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utility to convert Mongo documents to JSON serializable dicts

def serialize_doc(doc: dict) -> dict:
    if not doc:
        return doc
    doc = {**doc}
    _id = doc.get("_id")
    if isinstance(_id, ObjectId):
        doc["id"] = str(_id)
        del doc["_id"]
    # Convert datetimes to isoformat
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response

# ----------------------
# Todo API
# ----------------------

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    notes: Optional[str] = Field(None, max_length=2000)
    due_at: Optional[datetime] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    notes: Optional[str] = Field(None, max_length=2000)
    due_at: Optional[datetime] = None
    completed: Optional[bool] = None

TASK_COLLECTION = "task"

@app.get("/api/tasks", response_model=List[TaskOut])
def list_tasks() -> List[TaskOut]:
    docs = get_documents(TASK_COLLECTION, {}, None)
    return [TaskOut(**serialize_doc(d)) for d in docs]

@app.post("/api/tasks", response_model=TaskOut)
def create_task(payload: TaskCreate) -> TaskOut:
    data = Task(
        title=payload.title,
        notes=payload.notes,
        due_at=payload.due_at,
        completed=False,
    )
    _id = create_document(TASK_COLLECTION, data)
    # fetch inserted document
    doc = db[TASK_COLLECTION].find_one({"_id": ObjectId(_id)})
    return TaskOut(**serialize_doc(doc))

@app.patch("/api/tasks/{task_id}/toggle", response_model=TaskOut)
def toggle_task(task_id: str) -> TaskOut:
    try:
        oid = ObjectId(task_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")
    doc = db[TASK_COLLECTION].find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    new_completed = not doc.get("completed", False)
    db[TASK_COLLECTION].update_one({"_id": oid}, {"$set": {"completed": new_completed, "updated_at": datetime.utcnow()}})
    updated = db[TASK_COLLECTION].find_one({"_id": oid})
    return TaskOut(**serialize_doc(updated))

@app.put("/api/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: str, payload: TaskUpdate) -> TaskOut:
    try:
        oid = ObjectId(task_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    update_data["updated_at"] = datetime.utcnow()
    res = db[TASK_COLLECTION].update_one({"_id": oid}, {"$set": update_data})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    updated = db[TASK_COLLECTION].find_one({"_id": oid})
    return TaskOut(**serialize_doc(updated))

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    try:
        oid = ObjectId(task_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid task id")
    res = db[TASK_COLLECTION].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
