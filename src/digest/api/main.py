from fastapi import FastAPI

app = FastAPI(title="AI Email Digest")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
