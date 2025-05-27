# sam-dispatch

## Usage

```
$ sam-dispatch --help
usage: sam-dispatch [-h] config

Automated setup of test clients

positional arguments:
  config      Path to config

options:
  -h, --help  show this help message and exit
```

## Example config

```jsonc
{
  "name": "Example Scenario", // name of scenario
  "address": "127.0.0.1:8080", // port to run dispatcher on
  "type": "sam", // whether to use sam or denim infrastructure (valid: sam, denim)
  "clients": 1, // how many clients to register
  "groups": 1, // clients divided equally between groups
  "tickMillis": 1000, // how many milliseconds one tick corresponds to
  "durationTicks": 500, // time of experiment
  "messageSizeRange": [200, 500], // the size range clients will be sending messages in
  "denimProbability": 1, // how probable a client will be to send a denim message
  "replyProbability": [0.5, 0.95], // how probable a client will be to reply to a message
  "sendRateRange": [1, 5], // how fast a client will send a message, each client gets a random send rate, faster send rate will have less data in the messages and vice versa
  "replyRateRange": [1, 2], // how fast a client will reply to a message
  "staleReplyRange": [1, 1], // ticks before a client wont reply to a message
  "friendAlpha": 0.3, // seed the alpha in dirichlet distribution: [friendAlpha] * len(friends)
  "report": "report.json" // final report is saved to report/<name>.json
}
```

## Docker

1. build: `docker build --network=host -t sam-dispatch .`
2. run `docker run --rm -p 8080:8080 -v ./reports:/reports sam-dispatch example.json`
