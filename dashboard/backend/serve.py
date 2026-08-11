import uvicorn
from pathlib import Path
import sys

# Ensure backend directory is in path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

if __name__ == "__main__":
    from ingest import reload_store
    reload_store()
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

