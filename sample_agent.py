from strands import Agent
from strands_tools import calculator
from strands.models.ollama import OllamaModel

OLLAMA_HOST = 'localhost'
OLLAMA_MODEL = 'phi4-mini'

model = OllamaModel(
    host = f"http://{OLLAMA_HOST}:11434",
    model_id = OLLAMA_MODEL
)

agent = Agent(model = model, tools=[calculator])
agent("What is the square root of 1764")