# Mandatory Instructions — Docker Networking

These instructions MUST be followed when building or running any server, API, or service inside this Docker container.

## Server Binding

**Always bind to `0.0.0.0`, NEVER to `127.0.0.1` or `localhost`.**

Inside a Docker container, `127.0.0.1` only accepts connections from within the container itself. To make a server accessible from the host machine (your Mac), it must bind to `0.0.0.0`.

Examples:

```python
# Python (Flask)
app.run(host="0.0.0.0", port=PORT)

# Python (uvicorn/FastAPI)
uvicorn.run(app, host="0.0.0.0", port=PORT)
```

```javascript
// Node.js (Express)
app.listen(PORT, "0.0.0.0");

// Next.js / Vite
// Use --host 0.0.0.0 flag
```

```bash
# Generic CLI servers
--host 0.0.0.0 --port PORT
```

## Allocated Port Range

This project has been assigned the following port range:

```
START_PORT: 8000
END_PORT:   8004
```

You have **5 ports** available. Use them for any servers, APIs, dashboards, or services this project needs.

| Port | Suggested Use |
|------|---------------|
| 8000 | Primary server / API |
| 8001 | Secondary service / admin dashboard |
| 8002 | WebSocket server |
| 8003 | Development / hot-reload server |
| 8004 | Testing / debug server |

These ports are mapped 1:1 from the container to the host. A server on port 8000 inside the container is accessible at `http://localhost:8000` on the host machine.

## Important

- Do NOT use ports outside your allocated range — they will not be mapped to the host and other projects may conflict.
- If you need more than 5 ports, ask the user to update the port allocation.
- Always check if a port is in use before starting a server: `lsof -i :PORT` or `ss -tlnp | grep PORT`.
