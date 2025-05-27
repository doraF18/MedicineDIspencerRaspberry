from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from pathlib import Path
import json
import uvicorn
import asyncio
import threading

# TODO: Maybe also add wifi configuration options

class DeviceConfigurator:


    def __init__(self, config_path="device_config.json"):
        self.BASE_DIR = Path(__file__).resolve().parent
        self.config_path = Path(config_path)
        self.app = FastAPI()
        self._setup_routes()
        self.server = None

    def _setup_routes(self):
        @self.app.get("/", response_class=HTMLResponse)
        async def form_page():
            return HTMLResponse(
                content=Path(self.BASE_DIR / "static" / "index.html").read_text(),
                media_type="text/html"
            )

        @self.app.post("/")
        async def submit_form(email: str = Form(...), password: str = Form(...)):
            self._save_config({"email": email, "password": password})
            asyncio.create_task(self.stop_server())
            return HTMLResponse("<h3>Device Paired Successfully!</h3>")
        
    async def stop_server(self):
        """
        Stops the FastAPI server.
        This method is called after the form is submitted to stop the server gracefully.
        """
        await asyncio.sleep(5)
        if self.server:
            self.server.should_exit = True

    def _save_config(self, data: dict):
        with self.config_path.open("w") as f:
            json.dump(data, f, indent=4)

    def run(self, host="0.0.0.0", port=8000):
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
        )

        self.server = uvicorn.Server(config)
        thread = threading.Thread(target=self.server.run)
        thread.start()

# Usage Example:
# config = DeviceConfigurator()
# config.run()
