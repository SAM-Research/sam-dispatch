from fastapi import FastAPI
from argparse import ArgumentParser
import uvicorn
from .state import State, ClientReport
from fastapi import Request, Response, HTTPException
import asyncio

app = FastAPI()
state = None


def auth(request: Request):
    try:
        client_id = request.cookies.get("id")
    except:
        raise HTTPException(status_code=401)
    host = request.client.host
    _id = create_id(host, client_id)

    if not state.is_auth(_id):
        raise HTTPException(status_code=401)
    return _id


def create_id(host: str, id: str):
    return f"{host}#{id}"


@app.get("/client")
async def client(request: Request, response: Response):
    client_id = await state.next_client_id()
    response.set_cookie(key="id", value=client_id)
    client_data = await state.get_client(create_id(request.client.host, client_id))
    if client_data is None:
        raise HTTPException(status_code=403)
    return client_data


@app.get("/start")
async def start(request: Request):
    return await state.start(auth(request))


@app.post("/upload")
async def upload(request: Request, report: ClientReport):
    _id = auth(request)
    await state.report(_id, report)

    if not state.all_clients_have_uploaded:
        return
    state.save_report()


@app.get("/health")
async def health():
    return "OK"


async def setup_state(path: str):
    global state
    state = State(path)
    await state.init_state()
    return state.scenario.address.split(":")


def main():
    global state
    parser = ArgumentParser(
        "sam-dispatch", description="Automated setup of test clients"
    )
    parser.add_argument("config", help="Path to config")
    args = parser.parse_args()
    config_path: str = args.config

    ip, port = asyncio.run(setup_state(config_path))
    uvicorn.run("sam_dispatcher.server:app", host=ip, port=int(port))
