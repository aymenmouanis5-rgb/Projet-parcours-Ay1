"""Live viewer: follows Kafka, or replays a finished run. It only reads events.

Live:    uv run python -m filets.viewer
Replay:  uv run python -m filets.viewer --replay runs/<run>
"""

import argparse
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from confluent_kafka import Consumer, KafkaException, TopicPartition

from filets.agent import HAMLETS, fisher_name
from filets.bus import BROKER, TIMEOUT, TOPIC, ensure_topics
from filets.indicator import EmergenceIndicator
from filets.schemas import validate

PAGE = Path(__file__).with_name("viewer.html")
LISTED_FISHERS = 64


class Feed:
    """Events read so far, which the page fetches by position."""

    def __init__(self, source: str):
        self.source = source
        self.events: list[dict] = []
        self.indicator = EmergenceIndicator()
        self.finished = False
        self.lock = threading.Lock()

    def add(self, event: dict) -> None:
        with self.lock:
            self.events.append(event)
            self.indicator.add(event)

    def since(self, position: int) -> dict:
        with self.lock:
            return {"source": self.source, "finished": self.finished, "next": len(self.events),
                    "events": self.events[position:], "indicator": self.indicator.records}


def end_of_topic(consumer: Consumer, partition: TopicPartition) -> int:
    deadline = time.monotonic() + TIMEOUT
    while True:
        try:
            return consumer.get_watermark_offsets(partition, timeout=TIMEOUT)[1]
        except KafkaException:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


def connect() -> Consumer:
    """Attach to the end of the topic, so the viewer shows the next run that starts."""
    ensure_topics()
    consumer = Consumer({"bootstrap.servers": BROKER, "group.id": f"viewer-{time.time()}",
                         "enable.auto.commit": False})
    partition = TopicPartition(TOPIC, 0)
    partition.offset = end_of_topic(consumer, partition)
    consumer.assign([partition])
    return consumer


def follow_kafka(feed: Feed, consumer: Consumer) -> None:
    while True:
        message = consumer.poll(0.2)
        if message is None or message.error():
            continue
        try:
            event = json.loads(message.value())
        except ValueError:
            continue
        if not validate(event):  # the recorder sends the others to the dead-letter topic
            feed.add(event)


def replay_file(feed: Feed, path: Path, delay: float) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        feed.add(json.loads(line))
        time.sleep(delay)
    feed.finished = True


def make_handler(feed: Feed):
    fishers = [{"name": fisher_name(i), "hamlet": HAMLETS[i % len(HAMLETS)]} for i in range(LISTED_FISHERS)]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/fishers":
                self.send(json.dumps(fishers).encode(), "application/json")
            elif url.path == "/events":
                position = int(parse_qs(url.query).get("since", ["0"])[0])
                self.send(json.dumps(feed.since(position)).encode(), "application/json")
            else:
                self.send_error(404)

        def send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(prog="filets.viewer", description="Watch a FILETS run.")
    parser.add_argument("--replay", type=Path, help="run folder or events.jsonl to replay instead of following Kafka")
    parser.add_argument("--delay", type=float, default=0.03, help="seconds between replayed events")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="do not open the page")
    args = parser.parse_args()

    if args.replay:
        path = args.replay / "events.jsonl" if args.replay.is_dir() else args.replay
        feed = Feed(f"replay of {path.parent.name}")
        reader = threading.Thread(target=replay_file, args=(feed, path, args.delay), daemon=True)
    else:
        try:
            consumer = connect()
        except KafkaException as error:
            raise SystemExit(f"Cannot reach Kafka at {BROKER}. Start it with: docker compose up -d\n{error}")
        feed = Feed(f"live from {TOPIC}")
        reader = threading.Thread(target=follow_kafka, args=(feed, consumer), daemon=True)
    reader.start()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(feed))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Viewer on {url} ({feed.source}). Press Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
