"""Single-worker durable inbox. Do not rerun a successfully completed graph thread."""
import logging
from threading import Event, Thread
from time import sleep
from app.models import IncomingMessage, ExtractedVacancy, MatcherResult
from app.services.memory import History

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, settings, history: History, graph, sender):
        self.settings, self.history, self.graph, self.sender = settings, history, graph, sender
        self.stop = Event()
        self.worker = None

    def start(self):
        if self.worker is not None:
            return
        self.worker = Thread(target=self.run, daemon=True, name="job-matcher-worker")
        self.worker.start()

    def close(self):
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=10)

    def run(self):
        while not self.stop.is_set():
            pending = self.history.pending()
            if not pending:
                self.stop.wait(0.5)
                continue
            for msg in pending:
                if self.stop.is_set():
                    return
                try:
                    self.process(msg)
                except Exception as exc:
                    log.exception("Message processing failed: chat=%s message=%s", msg.chat_id, msg.message_id)
                    self.history.mark(msg, "failed", str(exc))
                    self.stop.wait(3)

    def process(self, msg: IncomingMessage):
        self.history.mark(msg, "processing")
        log.info("[Pipeline] processing chat=%s message=%s", msg.chat_id, msg.message_id)
        thread_id = f"message:{msg.chat_id}:{msg.message_id}"
        config = {"configurable": {"thread_id": thread_id}}
        state = self.graph.get_state(config)
        # Completed checkpoints are reused, so a restart cannot re-run the AI
        # for already evaluated messages. Interrupted checkpoints can resume.
        if state.values and not state.next:
            result = state.values
        elif state.values and state.next:
            result = self.graph.invoke(None, config=config)
        else:
            result = self.graph.invoke({"message": msg.model_dump(mode="json")}, config=config)

        if result.get("extractor_error"):
            self.history.mark(msg, "failed", result["extractor_error"])
            return
        had_errors = False
        for entry in result.get("decisions", []):
            idx = entry["vacancy_index"]
            vacancy = ExtractedVacancy.model_validate(result["python_vacancies"][idx])
            match = MatcherResult.model_validate(entry["result"])
            if self.history.is_sent(msg, idx):
                continue
            status = "eligible" if match.recommended else "skipped"
            if entry["error"]:
                status = "failed"
                had_errors = True
            self.history.decision(msg, idx, vacancy, match, status)
            if match.recommended:
                try:
                    self.sender.send(msg, match)
                    self.history.set_sent(msg, idx)
                    log.info("[Telegram] sent chat=%s message=%s vacancy_index=%d score=%d", msg.chat_id, msg.message_id, idx, match.score)
                except Exception:
                    had_errors = True
                    log.exception("Telegram send failed, may require manual reconciliation")
        self.history.mark(msg, "retry" if had_errors else "done")
        log.info("[Pipeline] finished chat=%s message=%s status=%s decisions=%d", msg.chat_id, msg.message_id, "retry" if had_errors else "done", len(result.get("decisions", [])))
