"""HTTP, worker and CLI share frozen inputs and the existing model gateway."""
from evonext.contracts.trajectory import ContractError
from .outcome import freeze_input, grade, result_record


class OutcomeService:
    def __init__(self, evidence, store, settings):
        self.evidence, self.store, self.settings = evidence, store, settings

    def create(self, request):
        previous = self.store.get(request.run_id)
        if previous:
            if previous["frozen"]["request"] != request.model_dump():
                from .store import RunConflict
                raise RunConflict("Run ID already has another request")
            # Replay preserves the original policy/model even after configuration updates.
            return previous
        return self.store.create(freeze_input(request, self.evidence, self.settings))

    def execute(self, run_id, gateway):
        row = self.store.get(run_id)
        if row is None:
            raise ContractError("Outcome run not found")
        if not self.store.claim(run_id):
            return self.store.get(run_id)
        frozen = row["frozen"]
        if (frozen["model"], frozen["endpoint"]) != (
                self.settings.model_name, self.settings.model_base_url):
            record = result_record(frozen, execution="error", error="configured_model_route_changed")
        else:
            record = grade(frozen, self.evidence, gateway)
        self.store.finish(run_id, record)
        return self.store.get(run_id)
