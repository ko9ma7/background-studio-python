# Architecture

```text
Upload / CLI
    │
    ├─ image validation + size limit
    │
    ├─ RembgEngine (cached ONNX session)
    │       └─ transparent RGBA cutout
    │
    ├─ compose: transparent / color / image / blur / shadow
    │
    └─ PNG response

Video upload
    │
    ├─ queued in the in-process JobStore
    ├─ FFmpeg extracts bounded-size PNG frames
    ├─ the same image engine processes each frame
    ├─ FFmpeg encodes WebM alpha or MP4 composite and remuxes audio
    └─ status + download endpoints
```

The in-process job store is intentionally small and easy to run. Its ceiling is
one server process; a production multi-replica deployment should replace it
with durable object storage and a real queue before accepting untrusted public
traffic.

Security boundaries:

- streamed upload limits are enforced before decoding;
- file extensions never determine whether an image is valid;
- uploaded filenames are not used as server paths;
- server work files live under one configured directory;
- no user file is sent to a third-party API;
- public internet deployment still needs authentication, rate limiting,
  malware scanning, TLS, and a reverse-proxy body limit.

