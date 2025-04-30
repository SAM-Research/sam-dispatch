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
    parser = ArgumentParser("sam-dispatch")
    parser.add_argument("scenario", help="Path to scenario toml")
    parser.add_argument("-a", "--address", default="127.0.0.1:8080")
    parser.add_argument("-r", "--reload", action="store_true")
    args = parser.parse_args()
    scenario_path: str = args.scenario
    addr: str = args.address
    ip, port = addr.split(":")

    state = State(scenario_path)

    uvicorn.run(
        "sam_dispatcher.server:app", host=ip, port=int(port), reload=args.reload
    )
