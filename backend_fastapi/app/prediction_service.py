from backend_fastapi.ai_engine.machine_analyzer import machine_analyzer
from digital_twin.simulator import run_digital_twin

def get_predictions():
    machines = run_digital_twin()
    return machine_analyzer.analyze_machines(machines)