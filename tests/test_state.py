import pytest
from sam_dispatcher.state import (
    State,
    Scenario,
    Report,
    ClientReport,
    MessageLog,
    StartInfo,
)
import math
import time
import asyncio

scenarios = [
    Scenario(
        name="test",
        type="denim-on-sam",
        clients=10,
        groups=[0.5, 0.5],
        tickMillis=10,
        durationTicks=10,
        messageSizeRange=(10, 20),
        denimProbability=0.1,
        sendRateRange=(1, 5),
        replyRateRange=(1, 2),
        replyProbability=(0.5, 0.95),
        staleReply=1,
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", scenarios)
async def test_can_get_client(scenario: Scenario):
    state = State(scenario)
    await state.init_state()
    client = await state.get_client("127.0.0.1")

    denim_friends = filter(lambda x: x.denim, client.friends.values())
    assert client is not None
    assert client.duration_ticks == state.scenario.duration_ticks
    assert client.tick_millis == state.scenario.tick_millis
    assert (
        state.scenario.send_rate_range[0]
        <= client.send_rate
        <= state.scenario.send_rate_range[1]
    )

    assert all(f.denim for f in denim_friends)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", scenarios)
async def test_groups_have_denim_connection(scenario: Scenario):
    state = State(scenario)
    await state.init_state()
    groups = len(state.scenario.groups)
    count = 0
    for c in state.clients.values():
        for f in c.friends.values():
            if f.denim:
                count += 1
    assert count == groups


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", scenarios)
async def test_no_friendless_clients(scenario: Scenario):
    state = State(scenario)
    await state.init_state()
    friend_counts = {f.username: len(f.friends) for f in state.clients.values()}
    friendless_clients = sum(1 for x in friend_counts.values() if x == 0)
    all_has_friends = all(friend_counts.values())
    print([len(x.friends) for x in state.clients.values()])
    assert (
        all_has_friends
    ), f"Expected all clients to have friends found '{friendless_clients}' without any"


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", scenarios)
async def test_client_amount_persists(scenario: Scenario):
    state = State(scenario)
    await state.init_state()
    expected = state.scenario.clients
    assert state.client_amount == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", scenarios)
async def test_client_friend_freqs_add_to_one(scenario: Scenario):
    state = State(scenario)
    await state.init_state()
    for client in state.clients.values():
        total = sum(f.frequency for f in client.friends.values())
        assert math.isclose(total, 1.0, rel_tol=1e-9), f"Sum was {total}"


class TestReportWriter:
    report = None

    def write(self, path: str, report: Report):
        self.report = report


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", scenarios)
async def test_ready_to_save(scenario: Scenario):
    writer = TestReportWriter()
    state = State(scenario, writer)
    await state.init_state()
    start_time = int(time.time())

    clients: list[tuple[str, str]] = []
    starts = []
    for i in range(state.scenario.clients):
        ip = str(i)
        client = await state.get_client(ip)
        clients.append((ip, client.username))
        await state.set_account_id(ip, f"account_{ip}")
        starts.append(state.start(ip))

    await asyncio.gather(*starts)

    expected_report = Report(
        scenario=scenario,
        ipAddresses={v: k for k, v in state.usernames.items()},
        clients=state.clients,
        reports=dict(),
    )
    for ip, user in clients:
        report = ClientReport(
            startTime=0,
            messages=[MessageLog(type="regular", to="x", from_="x", size=1, tick=10)],
        )
        expected_report.reports[user] = report
        await state.report(ip, report)
    state.save_report()
    report = writer.report
    assert report is not None
    assert report == expected_report
