from pydantic import BaseModel, Field
from typing import Tuple, Dict, Optional, List
import uuid
import random
import math
import time
from pathlib import Path
from asyncio import Lock
import asyncio
import numpy as np
from copy import deepcopy


class Scenario(BaseModel):
    name: str
    type: str = Field()
    address: str = Field(alias="address", default="127.0.0.1:8080")
    clients: int = Field(alias="clients")
    groups: int = Field(alias="groups")
    tick_millis: int = Field(alias="tickMillis")
    duration_ticks: int = Field(alias="durationTicks")
    message_size_range: Tuple[int, int] = Field(alias="messageSizeRange")
    denim_probability: float = Field(alias="denimProbability")
    send_rate_range: Tuple[int, int] = Field(alias="sendRateRange")
    reply_rate_range: Tuple[int, int] = Field(alias="replyRateRange")
    reply_probability: tuple[float, float] = Field(alias="replyProbability")
    stale_reply_range: tuple[int, int] = Field(alias="staleReplyRange")
    friend_alpha: float = Field(alias="friendAlpha")
    report: str = Field(alias="report", default="report.json")


class Friend(BaseModel):
    username: str = Field()
    frequency: float = Field()
    denim: bool = Field()


class Client(BaseModel):
    username: str = Field()
    client_type: str = Field(alias="clientType")
    message_size_range: Tuple[int, int] = Field(alias="messageSizeRange")
    send_rate: int = Field(alias="sendRate")
    reply_rate: int = Field(alias="replyRate")
    tick_millis: int = Field(alias="tickMillis")
    duration_ticks: int = Field(alias="durationTicks")
    denim_probability: float = Field(alias="denimProbability")
    reply_probability: float = Field(alias="replyProbability")
    stale_reply: int = Field(alias="staleReply")
    friends: Dict[str, Friend] = Field()


class MessageLog(BaseModel):
    type: str = Field()  # denim, regular
    to: str = Field()
    from_: str = Field(alias="from")
    size: int = Field()
    tick: int = Field()

    model_config = {"populate_by_name": True}


class ClientReport(BaseModel):
    start_time: int = Field(alias="startTime")
    messages: List[MessageLog]


class AccountId(BaseModel):
    account_id: str = Field(alias="accountId")


class Report(BaseModel):
    scenario: Scenario
    ip_addresses: Dict[str, str] = Field(alias="ipAddresses")
    clients: Dict[str, Client]
    reports: Dict[str, ClientReport]


class StartInfo(BaseModel):
    friends: dict[str, str] = Field()


class ReportWriter:
    def write(self, path: str, report: Report):
        pass


class FsReportWriter:
    def write(self, path: str, report: Report):
        _dir = Path("reports/")
        _dir.mkdir(exist_ok=True)
        with open(_dir / path, "w") as f:
            f.write(report.model_dump_json(indent=2, by_alias=True))


class State:
    def __init__(self, scenario: str | Scenario, writer: ReportWriter = None):
        self.lock = Lock()
        if isinstance(scenario, str):
            with open(scenario, "r") as f:
                self.scenario = Scenario.model_validate_json(f.read())
        else:
            self.scenario = scenario

        self.writer = writer
        if self.writer is None:
            self.writer = FsReportWriter()

        self.clients: dict[str, Client] = dict()
        self.free_clients: set[str] = set()

        # ip, username
        self.usernames: dict[str, str] = dict()
        self.ready_clients: set[str] = set()
        # username, account_id
        self.account_ids: dict[str, str] = dict()

        self.reports: dict[str, ClientReport] = dict()

        self.client_counter = 0
        self.saved = False

    def _reset(self):
        self.clients = dict()
        self.free_clients = set()
        self.usernames = dict()
        self.ready_clients = set()

        self.reports = dict()

        self.client_counter = 0
        self.saved = False

    async def next_client_id(self):
        id = self.client_counter
        async with self.lock:
            self.client_counter += 1
        return id

    def is_auth(self, ip_id: str):
        return ip_id in self.usernames

    @property
    def client_amount(self):
        return len(self.clients)

    @property
    def clients_ready(self):
        return (
            all(ip in self.ready_clients for ip in self.usernames)
            and all(user in self.account_ids for user in self.usernames.values())
            and len(self.free_clients) == 0
        )

    @property
    def all_clients_have_uploaded(self):
        usernames = set(self.usernames.values())
        has_reports = len(self.reports) == len(self.clients)

        return all(user in usernames for user in self.reports) and has_reports

    async def set_account_id(self, ip_id: str, account_id: AccountId):
        async with self.lock:
            username = self.usernames[ip_id]
            self.account_ids[username] = account_id

    async def start(self, ip_id: str) -> StartInfo:
        await self._ready(ip_id)
        while not self.clients_ready:
            await asyncio.sleep(0.5)

        friends = self.clients[self.usernames[ip_id]].friends
        friends = dict(map(lambda x: (x[0], self.account_ids[x[0]]), friends.items()))

        return StartInfo(friends=friends)

    async def get_client(self, ip_id: str) -> Optional[Client]:
        async with self.lock:
            if len(self.free_clients) == 0:
                return None
            name = self.free_clients.pop()
            self.usernames[ip_id] = name
            return self.clients[name]

    async def report(self, ip_id: str, report: ClientReport):
        async with self.lock:
            username = self.usernames[ip_id]
            self.reports[username] = report
            if self.all_clients_have_uploaded and not self.saved:
                self.saved = True
                await self.save_report()

    async def save_report(self):
        ips = {v: k.split("#")[0] for k, v in self.usernames.items()}
        report = Report(
            scenario=self.scenario,
            ipAddresses=ips,
            clients=self.clients,
            reports=self.reports,
        )
        self.writer.write(self.scenario.report, report)

    async def _ready(self, ip: str):
        async with self.lock:
            self.ready_clients.add(ip)

    @staticmethod
    def _init_client(
        username: str,
        client_type: str,
        msg_range: tuple[int, int],
        send_rate: int,
        tick_millis: int,
        duration_ticks: int,
        denim_prob: float,
        reply_prob: float,
        reply_rate: int,
        stale_reply: int,
    ):
        return Client(
            username=username,
            clientType=client_type,
            messageSizeRange=msg_range,
            sendRate=send_rate,
            tickMillis=tick_millis,
            durationTicks=duration_ticks,
            denimProbability=denim_prob,
            replyProbability=reply_prob,
            replyRate=reply_rate,
            staleReply=stale_reply,
            friends=dict(),
        )

    async def init_state(self):
        async with self.lock:
            self._reset()
            total_clients = self.scenario.clients
            tick_millis = self.scenario.tick_millis
            duration_ticks = self.scenario.duration_ticks
            clients = dict()

            # initialize clients
            for _ in range(total_clients):
                username = str(uuid.uuid4())
                msg_range, send_rate = self._get_sizes_and_rate()
                reply_rate = random.randint(*self.scenario.reply_rate_range)
                stale_reply = random.randint(*self.scenario.stale_reply_range)
                reply_prob = random.uniform(*self.scenario.reply_probability)
                clients[username] = State._init_client(
                    username,
                    self.scenario.type,
                    msg_range,
                    send_rate,
                    tick_millis,
                    duration_ticks,
                    self.scenario.denim_probability,
                    reply_prob=reply_prob,
                    reply_rate=reply_rate,
                    stale_reply=stale_reply,
                )

            self.clients = clients
            self._make_friends(self.clients)
            self.free_clients: set[str] = {c.username for c in self.clients.values()}

    def _make_friends(self, clients: dict[str, Client]):
        names = set(clients.keys())
        client_amount = len(names)
        groups: list[list[str]] = []

        fraction = client_amount / self.scenario.groups / client_amount
        for _ in range(self.scenario.groups):
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
                    username=friend, denim=False, frequency=0
                )

        for name, friend_name in denim_pairs.items():
            friend = Friend(
                username=friend_name,
                denim=True,
                frequency=0,
            )
            clients[name].friends[friend_name] = friend

        # create weighted friends
        for client in clients.values():
            friend_amount = len(client.friends)

            # dirichlet distribution for skewed friends
            samples = np.random.dirichlet([self.scenario.friend_alpha] * friend_amount)
            samples = [float(x) for x in samples]

            for freq, ab_friend in zip(samples, client.friends.values()):
                ab_friend.frequency = freq

        # make mutual friendships
        mutuals: dict[tuple, float] = dict()
        for client in clients.values():
            for f, ab_friend in client.friends.items():
                pair = tuple(sorted((client.username, f)))
                if pair in mutuals:
                    continue
                ab_freq = ab_friend.frequency
                ba_friend = clients[f].friends[client.username]
                ba_freq = ba_friend.frequency

                mutual = (ab_freq + ba_freq) / 2
                mutuals[pair] = mutual

        #  Normalize all mutual weights globally
        total = sum(mutuals.values())
        for pair in mutuals:
            mutuals[pair] /= total

        # Assign normalized frequency to both A and B
        for (a, b), freq in mutuals.items():
            clients[a].friends[b].frequency = freq
            clients[b].friends[a].frequency = freq

    def _get_sizes_and_rate(self):
        min_rate, max_rate = self.scenario.send_rate_range

        send_rate = random.randint(min_rate, max_rate)
        # normalized range [0, 1]
        dividend = send_rate - min_rate
        divisor = max_rate - min_rate
        if divisor == 0:
            norm_rate = 1
        else:
            norm_rate = dividend / divisor

        min_size, max_size = self.scenario.message_size_range

        # clients with high send rate tends to send smaller messages
        max_size = min_size + (max_size - min_size) * norm_rate

        return (min_size, int(max_size)), send_rate
