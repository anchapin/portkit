import sys
import os
from pathlib import Path

# Add backend/src and backend to path
sys.path.append(os.path.join(os.getcwd(), "backend", "src"))
sys.path.append(os.path.join(os.getcwd(), "backend"))
os.environ["SECRET_KEY"] = "debug-key"
os.environ["JWT_SECRET_KEY"] = "debug-key"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///backend/src/test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379"

from main import app

for route in app.routes:
    print(f"{route.path} {route.methods}")
