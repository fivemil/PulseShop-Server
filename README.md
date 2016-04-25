# PulseShop Server
[![Build Status](https://travis-ci.org/PulseShop/PulseShop-Server.svg?branch=master)](https://travis-ci.org/PulseShop/PulseShop-Server) [![Coverage Status](https://coveralls.io/repos/PulseShop/PulseShop-Server/badge.svg?branch=master&service=github)](https://coveralls.io/github/PulseShop/PulseShop-Server?branch=master) [![Slack Status](https://PulseShop-slackin-drwasho.herokuapp.com/badge.svg)](https://PulseShop-slackin-drwasho.herokuapp.com)

This repo contains the PulseShop networking daemon that can be used to access the p2p network. It establishes connections and maintains
a Kademlia style DHT. Rest and websocket APIs are available for clients to communicate with the daemon.

## Install

Pre-built installers which bundle the client and server components can be found [here](https://github.com/PulseShop/PulseShop-Installer/releases).

To install just this server:
```bash
pip install -r requirements.txt
```

Depending on your system configuration you may need to install some additional dependencies. You can find more detailed, OS specific, instructions [here](https://slack-files.com/T02FPGBKB-F0KJU1CLX-cbbcf8a02c).

## Usage

```bash
python PulseShopd.py start --help
```

```
usage: python PulseShopd.py start [<args>]

Start the PulseShop server

optional arguments:
  -h, --help            show this help message and exit
  -d, --daemon          run the server in the background as a daemon
  -t, --testnet         use the test network
  -l LOGLEVEL, --loglevel LOGLEVEL
                        set the logging level [debug, info, warning, error,
                        critical]
  -p PORT, --port PORT  set the network port
  -a ALLOWIP, --allowip ALLOWIP
                        only allow api connections from this ip
  -r RESTAPIPORT, --restapiport RESTAPIPORT
                        set the rest api port
  -w WEBSOCKETPORT, --websocketport WEBSOCKETPORT
                        set the websocket api port
  -b HEARTBEATPORT, --heartbeatport HEARTBEATPORT
                        set the heartbeat port
  --pidfile PIDFILE     name of the pid file
```

## License
PulseShop Server is licensed under the [MIT License](LICENSE).
