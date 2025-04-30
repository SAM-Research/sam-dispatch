from fastapi import FastAPI
from argparse import ArgumentParser
import uvicorn
from .state import State, ClientReport
from fastapi.responses import JSONResponse
from fastapi import Request

app = FastAPI()
state = None


@app.get("/client")
async def client(request: Request):
    client_data = state.get_client(request.client.host)
    if client_data is None:
        return JSONResponse(
            status_code=403, content={"error": "Clients have been depleted"}
        )
    return client_data


@app.post("/ready")
async def ready(request: Request):
    state.ready(request.client.host)


@app.get("/start")
async def start():
    return {"start": state.clients_ready, "epoch": state.start_time}


@app.post("/upload")
async def upload(request: Request, report: ClientReport):
    state.report(request.client.host, report)


def main():
    global state
    parser = ArgumentParser(
        "sam-dispatch", description="Automated setup of test clients"
    )
    parser.add_argument("config", help="Path to config")
    args = parser.parse_args()
    config_path: str = args.config

    state = State(config_path)

    ip, port = state.scenario.address.split(":")

    uvicorn.run("sam_dispatcher.server:app", host=ip, port=int(port))
