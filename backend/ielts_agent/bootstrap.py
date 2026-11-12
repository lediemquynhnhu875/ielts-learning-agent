"""Composition root: wire provider runtimes into explicit use-case agents."""

from .agents.uc04.generator import ItemGenerationAgent
from .agents.uc04.safety import ContentSafetyAgent
from .agents.uc04.solver import BlindSolverAgent
from .agents.uc04.team import UC04Agents
from .core.config import Settings
from .infrastructure.llm.client import JsonLLMClient


def build_uc04_agents(settings: Settings, *, generator_client=None, solver_client=None) -> UC04Agents:
    generator_runtime = JsonLLMClient(settings, "generator", client=generator_client)
    solver_runtime = JsonLLMClient(settings, "solver", client=solver_client)
    return UC04Agents(
        generator=ItemGenerationAgent(generator_runtime),
        solver=BlindSolverAgent(solver_runtime),
        safety=ContentSafetyAgent(generator_runtime),
    )
