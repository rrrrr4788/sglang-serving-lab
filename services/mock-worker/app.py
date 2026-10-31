import asyncio
from contextlib import asynccontextmanager, suppress
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from uuid import uuid4
from pydantic import AliasChoices, BaseModel, Field

WORKER_ID = os.environ.get('WORKER_ID', 'worker-a')
BOOT_DELAY_S = float(os.environ.get('BOOT_DELAY_S', '15'))
MAX_INFLIGHT = int(os.environ.get('MAX_INFLIGHT', '2'))
DEFAULT_DELAY_S = float(os.environ.get("DEFAULT_DELAY_S", "0.2"))

@asynccontextmanager
async def lifespan(app):
    app.state.lock = asyncio.Lock()
    app.state.phase = 'starting'
    app.state.inflight = 0

    async def warm_up():
        await asyncio.sleep(BOOT_DELAY_S)
        # A concurrent drain must not be reversed by warm-up.
        async with app.state.lock:
            if app.state.phase == 'starting':
                app.state.phase = 'ready'

    loader = asyncio.create_task(warm_up())
    try:
        yield
    finally:
        loader.cancel()
        with suppress(asyncio.CancelledError):
            await loader


app = FastAPI(lifespan=lifespan)


class GenerateRequest(BaseModel):
    request_id: str = Field(
        default_factory=lambda: uuid4().hex,
        validation_alias=AliasChoices("rid", "request_id"),
    )
    stream: bool = False
    delay_s: float = Field(
        default=DEFAULT_DELAY_S,
        ge=0.1,
        le=30,
        validate_default=True,
    )


async def snapshot():
    async with app.state.lock:
        return {
            'worker_id': WORKER_ID,
            'phase': app.state.phase,
            'inflight': app.state.inflight,
            'ready': app.state.phase == 'ready',
        }


@app.get('/health/live')
async def live():
    return {'alive': True, 'worker_id': WORKER_ID}


@app.get('/status')
async def status():
    return await snapshot()


@app.get('/health')
async def ready():
    state = await snapshot()
    # Readiness is distinct from process liveness.
    status_code = 200
    if state['phase'] != 'ready':
        status_code = 503
    return JSONResponse(state, status_code)

@app.get("/server_info")
async def server_info():
    return {
        "served_model_name": "mock-model",
        "tp_size": 1,
        "dp_size": 1,
        "mock": True,
    }

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    state = await snapshot()
    return (
        "# TYPE mock_worker_inflight gauge\n"
        f"mock_worker_inflight {state['inflight']}\n"
        "# TYPE mock_worker_ready gauge\n"
        f"mock_worker_ready {int(state['ready'])}\n"
    )

@app.get("/model_info")
async def model_info():
    return {"is_generation": True, "mock": True}

@app.post('/generate')
async def generate(req: GenerateRequest):
    if req.stream:
        raise HTTPException(
            status_code=400,
            detail="mock only supports non-streaming",
        )

    # Admission and counter increment share the same critical section.
    # Rejected requests never enter the completion decrement path.
    async with app.state.lock:
        if app.state.phase != 'ready':
            raise HTTPException(
                status_code=503,
                detail='Worker is not ready'
            )

        if app.state.inflight >= MAX_INFLIGHT:
            raise HTTPException(
                status_code=503,
                detail='Worker is at capacity'
            )

        app.state.inflight += 1

    try:
        await asyncio.sleep(req.delay_s)
        return {'mock': True, 'worker_id': WORKER_ID,
                'request_id': req.request_id, 'delay_s': req.delay_s}
    finally:
        # The last admitted request completes the drain transition.
        async with app.state.lock:
            app.state.inflight -= 1

            if app.state.phase == 'draining' and app.state.inflight == 0:
                app.state.phase = 'drained'


@app.post('/admin/drain')
async def drain():
    # Stop admission; repeated drain calls keep the state stable.
    # The process stays alive while admitted requests finish.
    async with app.state.lock:
        if app.state.phase in ['starting', 'ready']:
            app.state.phase = 'draining'

        if app.state.inflight == 0:
            app.state.phase = 'drained'

    return await snapshot()
