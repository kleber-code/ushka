#!/usr/bin/env bash
# usage: run.sh <label> <module> [ENV=...]   server pinned to cpu 2, clients to cpus 4-7
PY=${PYTHON:-python}
label=$1; mod=$2; shift 2
cd "$(dirname "$0")"
env "$@" taskset -c 2 $PY -c "import uvicorn;uvicorn.run('$mod:app',port=8810,log_level='error',access_log=False)" >/dev/null 2>&1 &
pid=$!
for i in $(seq 40); do curl -s -o /dev/null localhost:8810/ && break; sleep 0.25; done
rss=$(ps -o rss= -p $pid | awk '{printf "%.0f", $1/1024}')
run() { taskset -c 4-7 $PY load.py 8810 "$@"; }
h=$(run GET / 4 32 2 6)
t=$(run GET "/items/42?q=abc" 4 32 2 6)
p=$(run POST /items 4 32 2 6 '{"name":"pen","price":2.5}')
echo "$label | rss=${rss}MB | hello: $h | typed: $t | post: $p"
kill $pid 2>/dev/null; wait $pid 2>/dev/null
