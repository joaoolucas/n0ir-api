#!/usr/bin/env python3

import uvicorn
import os
from app.core.config import settings

if __name__ == "__main__":
    # Use Railway's PORT or fallback to settings
    port = int(os.environ.get("PORT", settings.port))
    host = "0.0.0.0"  # Always bind to all interfaces for Railway
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=settings.reload,
        log_level=settings.log_level
    )