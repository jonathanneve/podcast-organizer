# Podcast Organizer

To run this project, the easiest is to build the docker image, so all the dependencies are self-contained:

```
docker compose up --build
```

This will initialize 3 containers: a local PostgreSQL database, the Python backend for the system, and the UI front-end. When everything is up, you can access the UI at:

http://localhost:5173/
