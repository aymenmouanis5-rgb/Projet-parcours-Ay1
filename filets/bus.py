"""Event transport: the simulation publishes to Kafka, a consumer validates and records.

The simulation never writes events.jsonl itself, so the log only holds what went through Kafka.
"""

import itertools
import json
import threading
import time
from pathlib import Path

from confluent_kafka import Consumer, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

from filets.schemas import SCHEMA_VERSION, validate

BROKER = "localhost:9092"
TOPIC = "filets.events"
DEAD_LETTER_TOPIC = "filets.events.dlq"
TIMEOUT = 10.0
RECORDER_TIMEOUT = 60.0


def ensure_topics() -> None:
    """Create the topics. One partition keeps a total order, which replay needs."""
    admin = AdminClient({"bootstrap.servers": BROKER})
    wanted = [NewTopic(name, num_partitions=1, replication_factor=1) for name in (TOPIC, DEAD_LETTER_TOPIC)]
    existing = admin.list_topics(timeout=TIMEOUT).topics
    missing = [topic for topic in wanted if topic.topic not in existing]
    for future in admin.create_topics(missing).values() if missing else ():
        future.result(TIMEOUT)


class Recorder(threading.Thread):
    """Consume one run's events: conforming ones go to the log, the others to the dead-letter topic."""

    def __init__(self, run_id: str, path: Path):
        super().__init__(daemon=True)
        self.run_id = run_id.encode()
        self.path = path
        self.rejected = 0
        self.dead_letters = Producer({"bootstrap.servers": BROKER})
        self.consumer = Consumer({"bootstrap.servers": BROKER, "group.id": run_id, "enable.auto.commit": False})
        partition = TopicPartition(TOPIC, 0)
        partition.offset = self._end_of_topic(partition)  # skip what earlier runs left there
        self.consumer.assign([partition])

    def _end_of_topic(self, partition: TopicPartition) -> int:
        """Read the end offset, waiting out the moment a fresh broker has no leader yet."""
        deadline = time.monotonic() + TIMEOUT
        while True:
            try:
                return self.consumer.get_watermark_offsets(partition, timeout=TIMEOUT)[1]
            except KafkaException:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)

    def run(self) -> None:
        with self.path.open("w", encoding="utf-8") as log:
            finished = False
            while not finished:
                message = self.consumer.poll(0.2)
                if message is None:
                    continue
                if message.error():
                    raise KafkaException(message.error())
                if message.key() == self.run_id:
                    finished = self._record(message.value(), log)
        self.dead_letters.flush(TIMEOUT)
        self.consumer.close()

    def _record(self, raw: bytes, log) -> bool:
        """Handle one event, and return True when it ends the run."""
        try:
            event = json.loads(raw)
            errors = validate(event)
        except ValueError:
            event, errors = None, ["not JSON"]
        if errors:
            self.rejected += 1
            self.dead_letters.produce(DEAD_LETTER_TOPIC, key=self.run_id,
                                      value=json.dumps({"errors": errors, "raw": raw.decode(errors="replace")}))
            self.dead_letters.poll(0)
        else:
            event["consumed_at"] = time.time()
            log.write(json.dumps(event, ensure_ascii=False) + "\n")
            log.flush()
        return isinstance(event, dict) and event.get("type") == "run_ended"


class EventBus:
    def __init__(self, run_id: str, path: Path, clock):
        path.parent.mkdir(parents=True, exist_ok=True)
        ensure_topics()
        self.run_id = run_id
        self.clock = clock
        self.sequence = itertools.count(1)
        self.producer = Producer({"bootstrap.servers": BROKER})
        self.recorder = Recorder(run_id, path)
        self.recorder.start()

    def write(self, type_: str, season: int, **fields) -> None:
        event = {"v": SCHEMA_VERSION, "id": f"{self.run_id}-{next(self.sequence):05d}", "run": self.run_id,
                 "type": type_, "season": season,
                 "sim_time": round(self.clock.now(), 4), "processed_at": time.time(), **fields}
        self.producer.produce(TOPIC, key=self.run_id, value=json.dumps(event, ensure_ascii=False))
        self.producer.poll(0)

    def close(self) -> int:
        """Wait until the recorder has seen the end of the run, and return the events it rejected."""
        self.producer.flush(TIMEOUT)
        self.recorder.join(RECORDER_TIMEOUT)
        if self.recorder.is_alive():
            raise RuntimeError(f"the recorder did not see the end of run {self.run_id}")
        return self.recorder.rejected
