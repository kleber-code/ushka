"""Tiny multi-process HTTP/1.1 keep-alive load generator (no wrk/ab on this machine)."""
import asyncio, json, multiprocessing as mp, sys, time

def request_bytes(method, path, body=None):
    head = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nAccept: */*\r\n"
    if body is not None:
        head += f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
    return (head + "\r\n").encode() + (body or b"")

async def read_response(reader):
    head = await reader.readuntil(b"\r\n\r\n")
    status = int(head[9:12])
    low = head.lower()
    if b"transfer-encoding: chunked" in low:
        while True:
            size = int((await reader.readline()).strip(), 16)
            await reader.readexactly(size + 2)
            if size == 0:
                break
    else:
        i = low.find(b"content-length:")
        if i >= 0:
            n = int(low[i + 15: low.index(b"\r\n", i)])
            await reader.readexactly(n)
    return status

async def conn(port, req, stop_at, warm_until, lat, counts):
    r, w = await asyncio.open_connection("127.0.0.1", port)
    while True:
        t = time.perf_counter()
        if t >= stop_at: break
        w.write(req)
        try:
            status = await read_response(r)
        except Exception:
            counts["err"] += 1
            r, w = await asyncio.open_connection("127.0.0.1", port); continue
        if t >= warm_until:
            if 200 <= status < 300:
                counts["ok"] += 1
                if counts["ok"] % 7 == 0: lat.append(time.perf_counter() - t)
            else:
                counts["bad"] += 1
    w.close()

def worker(args):
    port, req, conns, warm, dur = args
    lat, counts = [], {"ok": 0, "err": 0, "bad": 0}
    async def main():
        t0 = time.perf_counter()
        await asyncio.gather(*[conn(port, req, t0 + warm + dur, t0 + warm, lat, counts) for _ in range(conns)])
    asyncio.run(main())
    return counts, lat

if __name__ == "__main__":
    port, method, path, procs, conns, warm, dur = sys.argv[1:8]
    body = sys.argv[8].encode() if len(sys.argv) > 8 else None
    req = request_bytes(method, path, body)
    with mp.Pool(int(procs)) as pool:
        res = pool.map(worker, [(int(port), req, int(conns), float(warm), float(dur))] * int(procs))
    ok = sum(c["ok"] for c, _ in res); err = sum(c["err"] for c, _ in res); bad = sum(c["bad"] for c, _ in res)
    lat = sorted(x for _, l in res for x in l)
    pct = lambda p: lat[int(len(lat) * p)] * 1000 if lat else 0
    print(json.dumps({"rps": round(ok / float(dur)), "p50_ms": round(pct(.5), 2), "p99_ms": round(pct(.99), 2), "non2xx": bad, "errors": err}))
