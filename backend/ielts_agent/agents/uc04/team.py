"""Named specialist agents composed by the UC-04 orchestrator."""

from dataclasses import dataclass

from .generator import ItemGenerationAgent
from .safety import ContentSafetyAgent
from .solver import BlindSolverAgent


@dataclass
class UC04Agents:
    generator: ItemGenerationAgent
    solver: BlindSolverAgent
    safety: ContentSafetyAgent

    @property
    def metadata(self) -> dict:
        return {**self.generator.metadata, **self.solver.metadata, **self.safety.metadata}

    def close(self) -> None:
        # Safety and generation intentionally share a transport configuration,
        # while each invocation remains stateless. Close that transport once.
        clients = {id(agent.client): agent.client for agent in (self.generator, self.solver, self.safety)}
        for client in clients.values():
            client.close()
