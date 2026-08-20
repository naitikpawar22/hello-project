import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
<<<<<<< HEAD
        host=os.getenv("EXAMFORGE_HOST", "0.0.0.0"),
=======
        host=os.getenv("EXAMFORGE_HOST", "127.0.0.1"),
>>>>>>> 00cdc5ce5c2c164af42ff31e6595073d105d2b0b
        port=int(os.getenv("EXAMFORGE_PORT", "5000")),
        debug=os.getenv("EXAMFORGE_DEBUG", "1") == "1",
    )
