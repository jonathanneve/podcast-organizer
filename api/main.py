from fastapi import FastAPI

app = FastAPI(title="Podcast Organizer API")


@app.get("/health")
def health_check():
    return {"status": "ok"}
