import os
import uvicorn
from app.server import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8002))
    print(f"Starting Task 3 Meeting-to-Scope Service on port {port}...")
    uvicorn.run("app.server:app", host="0.0.0.0", port=port, reload=False)
