"""Launcher for the browser UI: `rtu-web` or `python -m web.serve`."""
import os


def main():
    import uvicorn

    try:
        from dotenv import load_dotenv
        from mcp_server.config_loader import PROJECT_ROOT
        load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
    except Exception:
        pass

    host = os.environ.get("WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("WEB_PORT", "8080")))
    uvicorn.run("web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
