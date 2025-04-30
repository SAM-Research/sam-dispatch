from pydantic import BaseModel, Field
from typing import Tuple, Dict, Optional, List
import uuid
import random
import math
import time
from pathlib import Path


class Scenario(BaseModel):
    name: str
    address: str = Field(alias="address", default="127.0.0.1:8080")
    clients: int = Field(alias="clients")
    groups: List[float] = Field(alias="groups")
    tick_millis: int = Field(alias="tickMillis")
    duration_ticks: int = Field(alias="durationTicks")
    message_size_range: Tuple[int, int] = Field(alias="messageSizeRange")
    denim_probability: float = Field(alias="denimProbability")
    send_rate_range: Tuple[int, int] = Field(alias="sendRateRange")
    start_epoch: int = Field(alias="startEpoch", default=10)
    report: str = Field(alias="report", default="report.json")


class Friend(BaseModel):
    username: str = Field()
    frequency: float = Field()
    denim_probability: float = Field(alias="denimProbability")


class Client(BaseModel):
    username: str = Field()
    message_size_range: Tuple[int, int] = Field(alias="messageSizeRange")
    send_rate: int = Field(alias="sendRate")
    tick_millis: int = Field(alias="tickMillis")
    duration_ticks: int = Field(alias="durationTicks")
    friends: Dict[str, Friend]


class MessageLog(BaseModel):
    type: str = Field()  # denim, regular, status, other protocol
    to: str = Field()  # server or username
    from_: str = Field(alias="from")
    size: int = Field()
    timestamp: int = Field()

    model_config = {"populate_by_name": True}


class ClientReport(BaseModel):
    websocket_port: int = Field(alias="websocketPort")
    messages: List[MessageLog]


class Report(BaseModel):
    scenario: Scenario
    clients: dict[str, Client]
    reports: dict[str, ClientReport]


class ReportWriter:
    def write(self, path: str, report: Report):
        pass


class FsReportWriter:
    def write(self, path: str, report: Report):
        _dir = Path("reports/")
        _dir.mkdir(exist_ok=True)
        with open(_dir / path, "w") as f:
            f.write(report.model_dump_json(indent=2))


class State:
    def __init__(self, scenario: str | Scenario, writer: ReportWriter = None):
        if isinstance(scenario, str):
            with open(scenario, "r") as f:
                self.scenario = Scenario.model_validate_json(f.read())
        else:
            self.scenario = scenario

        self.writer = writer
        if self.writer is None:
            self.writer = FsReportWriter()

        if len(self.scenario.groups) == 0:
            self.scenario.groups.append(1.0)
        if sum(self.scenario.groups) != 1:
            raise RuntimeError("Groups must add up to 1")

        self.clients: dict[str, Client] = dict()
        self.create_clients()
        self.free_clients: set[str] = {c.username for c in self.clients.values()}

        # ip, username
        self.ips: dict[str, str] = dict()
        self.ready_clients: set[str] = set()
        self.start_time = int(time.time())

        self.reports: dict[str, ClientReport] = dict()

    @property
    def client_amount(self):
        return len(self.clients)

    @property
    def clients_ready(self):
        return (
            all(ip in self.ready_clients for ip in self.ips)
            and len(self.free_clients) == 0
        )

    def ready(self, ip: str):
        self.ready_clients.add(ip)
        if self.clients_ready:
            self.start_time = int(time.time()) + self.scenario.start_epoch

    def get_client(self, ip: str) -> Optional[Client]:
        if len(self.free_clients) == 0:
            return None
        name = self.free_clients.pop()
        self.ips[ip] = name
        return self.clients[name]

    def report(self, ip: str, report: ClientReport):
        username = self.ips[ip]
        self.reports[username] = report
        usernames = set(self.ips.values())
        if not all(user in usernames for user in self.reports):
            return
        self.save_report()

    def save_report(self):
        report = Report(
            scenario=self.scenario, clients=self.clients, reports=self.reports
        )
        self.writer.write(self.scenario.report, report)

    @staticmethod
    def init_client(
        username: str,
        msg_range: tuple[int, int],
        send_rate: int,
        tick_millis: int,
        duration_ticks: int,
    ):
        return Client(
            username=username,
            messageSizeRange=msg_range,
            sendRate=send_rate,
            tickMillis=tick_millis,
            durationTicks=duration_ticks,
            friends=dict(),
        )

    def create_clients(self):
        total_clients = self.scenario.clients
        tick_millis = self.scenario.tick_millis
        duration_ticks = self.scenario.duration_ticks
        clients = dict()

        # initialize clients
        for _ in range(total_clients):
            username = str(uuid.uuid4())
            msg_range, send_rate = self.get_sizes_and_rate()
            clients[username] = State.init_client(
                username,
                msg_range,
                send_rate,
                tick_millis,
                duration_ticks,
            )

        self.clients = clients
        self.make_friends(self.clients)

    def make_friends(self, clients: dict[str, Client]):
        names = set(clients.keys())
        client_amount = len(names)
        groups: list[list[str]] = []
        for fraction in self.scenario.groups:
            group_amount = math.floor(client_amount * fraction)
            current_group = [names.pop() for _ in range(group_amount)]
            groups.append(current_group)

        if len(names) != 0:
            for group in groups:
                if len(names) == 0:
                    break
                group.append(names.pop())

        denim_pairs: dict[str, str] = dict()
        prev = None
        for group in groups:
            if prev is None:
                prev = group[0]
            else:
                denim_pairs[prev] = group[0]
                denim_pairs[group[0]] = prev
                prev = None

        friends: dict[str, set[str]] = dict()
        for group in groups:
            for name in group:
                friends[name] = {n for n in group if n != name}

        for name, group in friends.items():
            for friend in group:
                clients[name].friends[friend] = Friend(
                    username=friend, denimProbability=0.0, frequency=0
                )

        for name, friend_name in denim_pairs.items():
            friend = Friend(
                username=friend_name,
                denimProbability=self.scenario.denim_probability,
                frequency=0,
            )
            clients[name].friends[friend_name] = friend

        for client in clients.values():
            friend_amount = len(client.friends)
            samples = [random.random() for _ in range(friend_amount)]
            total = sum(samples)
            frequencies = [x / total for x in samples]
            for freq, friend in zip(frequencies, client.friends.values()):
                friend.frequency = freq

    def get_sizes_and_rate(self):
        min_rate, max_rate = self.scenario.send_rate_range

        send_rate = random.randint(min_rate, max_rate)
        # normalized range [0, 1]
        norm_rate = (send_rate - min_rate) / (max_rate - min_rate)

        min_size, max_size = self.scenario.message_size_range

        # clients with high send rate tends to send smaller messages
        max_size = min_size + (max_size - min_size) * norm_rate

        return (min_size, int(max_size)), send_rate
