import pytest
from sam_dispatcher.state import State, Scenario, Report, ClientReport, MessageLog
import math

scenarios = [
    Scenario(
        name="test",
        clients=10,
        groups=[0.5, 0.5],
        tickMillis=10,
        durationTicks=10,
        messageSizeRange=(10, 20),
        denimProbability=0.1,
        sendRateRange=(1, 5),
    ),
]


@pytest.mark.parametrize("scenario", scenarios)
def test_can_get_client(scenario: Scenario):
    state = State(scenario)

    client = state.get_client("127.0.0.1")

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


@pytest.mark.parametrize("scenario", scenarios)
def test_groups_have_denim_connection(scenario: Scenario):
    state = State(scenario)

    groups = len(state.scenario.groups)
    count = 0
    for c in state.clients.values():
        for f in c.friends.values():
            if f.denim:
                count += 1
    assert count == groups


@pytest.mark.parametrize("scenario", scenarios)
def test_no_friendless_clients(scenario: Scenario):
    state = State(scenario)
    friend_counts = {f.username: len(f.friends) for f in state.clients.values()}
    friendless_clients = sum(1 for x in friend_counts.values() if x == 0)
    all_has_friends = all(friend_counts.values())
    print([len(x.friends) for x in state.clients.values()])
    assert (
        all_has_friends
    ), f"Expected all clients to have friends found '{friendless_clients}' without any"


@pytest.mark.parametrize("scenario", scenarios)
def test_client_amount_persists(scenario: Scenario):
    state = State(scenario)
    expected = state.scenario.clients
    assert state.client_amount == expected


@pytest.mark.parametrize("scenario", scenarios)
def test_client_friend_freqs_add_to_one(scenario: Scenario):
    state = State(scenario)
    for client in state.clients.values():
        total = sum(f.frequency for f in client.friends.values())
        assert math.isclose(total, 1.0, rel_tol=1e-9), f"Sum was {total}"


class TestReportWriter:
    def write(self, path: str, report: Report):
        self.report = report


@pytest.mark.parametrize("scenario", scenarios)
def test_ready_to_save(scenario: Scenario):
    writer = TestReportWriter()
    state = State(scenario, writer)
    time = state.start_time

    clients: list[tuple[str, str]] = []
    for i in range(state.scenario.clients):
        ip = str(i)
        client = state.get_client(ip)
        state.ready(ip)
        clients.append((ip, client.username))

    assert state.clients_ready
    assert 10 <= state.start_time - time

    expected_report = Report(scenario=scenario, clients=state.clients, reports=dict())
    for ip, user in clients:
        report = ClientReport(
            websocketPort=43434,
            messages=[
                MessageLog(type="regular", to="x", from_="x", size=1, timestamp=10)
            ],
        )
        expected_report.reports[user] = report
        state.report(ip, report)

    report = writer.report
    assert report is not None
    assert report == expected_report
