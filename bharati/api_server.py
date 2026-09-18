import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from simulation.engine import SimulationEngine
from typing import List
from fastapi.middleware.cors import CORSMiddleware

# Initialize FastAPI App
app = FastAPI(title="Bharati Digital Twin API", version="1.0.0")

# Allow CORS for all frontend dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the God Engine (Normal speed 1x, dynamically accelerates when faults are active)
engine = SimulationEngine(use_real_clock=False, time_acceleration=1)
connected_clients: List[WebSocket] = []

class FaultRequest(BaseModel):
    fault_id: str
    severity: float = 1.0

class WorkOrderRequest(BaseModel):
    fault_id: str

@app.on_event("startup")
async def startup_event():
    """Start the physics simulation loop asynchronously on boot."""
    logging.info("Starting Background Physics Simulation Loop...")
    asyncio.create_task(simulation_loop())

async def simulation_loop():
    """The main heartbeat of the Digital Twin."""
    while True:
        # Dynamic Time Acceleration: Fast-forward ONLY when there's an active fault or repair
        if engine.fault_manager.active_faults or engine.inventory_model.active_repairs:
            engine.time_acceleration = 300  # Fast-forward mode (1 real min = 5 sim hours)
        else:
            engine.time_acceleration = 1    # Normal mode (1 real min = 1 sim min, 1x)

        # Tick the engine (Calculates Thermodynamics, Biology, Weibull maths, etc.)
        state = engine.step()
        
        # Broadcast the massive state dictionary to all connected frontend dashboards
        if connected_clients:
            dead_clients = []
            for client in connected_clients:
                try:
                    await client.send_json(state)
                except Exception:
                    dead_clients.append(client)
                    
            for c in dead_clients:
                if c in connected_clients:
                    connected_clients.remove(c)
                
        # Simulate at 1Hz (1 real second = 1 simulation second at 1x)
        await asyncio.sleep(1.0)

@app.get("/state")
async def get_state():
    """Returns a single JSON snapshot of the entire station."""
    return engine.state

@app.get("/faults/list")
async def get_faults_list():
    """Returns all dynamically registered Single Points of Failure."""
    return engine.fault_manager.registered_spofs

@app.post("/fault/trigger")
async def trigger_fault(req: FaultRequest):
    """Allows a dashboard to inject a physical fault instantly."""
    engine.fault_manager.trigger(req.fault_id, req.severity)
    return {"status": "success", "message": f"Injected fault: {req.fault_id}"}

@app.post("/work_order/dispatch")
async def dispatch_work_order(req: WorkOrderRequest):
    """Allows a dashboard to dispatch a mechanic to fix a fault."""
    success = engine.inventory_model.dispatch_work_order(req.fault_id, engine.state)
    return {
        "status": "success" if success else "failed",
        "message": f"Work order for {req.fault_id} dispatched to MTTR queue." if success else "Work order rejected (No stock or active repair)."
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket stream for 1Hz Live Telemetry."""
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            # Keep connection alive; clients can send messages here if needed
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
