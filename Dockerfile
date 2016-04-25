FROM ubuntu:14.04

MAINTAINER Joshua Sindy <josh@root.bz>
# Examples
# docker build -t observer .
# docker run --rm -it -e flags="--help" observer
# docker run -d --name observer -e flags="--testnet" observer
# docker logs observer

RUN apt-get update
RUN apt-get install -y python-dev python-pip build-essential git libffi-dev libssl-dev
RUN pip install pyopenssl ndg-httpsclient pyasn1
RUN pip install --upgrade pip virtualenv
RUN pip install mock coverage nose pylint
RUN git clone https://github.com/PulseShop/PulseShop-Server.git
WORKDIR /PulseShop-Server/
RUN pip install -r requirements.txt && pip install -r test_requirements.txt
RUN make
RUN adduser --disabled-password --gecos \"\" PulseShop
RUN chown -R PulseShop:PulseShop /PulseShop-Server

USER PulseShop
CMD python PulseShopd.py start $flags
