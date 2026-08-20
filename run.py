import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.getenv("EXAMFORGE_HOST", "0.0.0.0"),
        port=int(os.getenv("EXAMFORGE_PORT", "5000")),
        debug=os.getenv("EXAMFORGE_DEBUG", "1") == "1",
    )
