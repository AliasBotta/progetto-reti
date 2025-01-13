from dataclasses import dataclass, field
from typing import List, Dict, Union

from mininet.net import Mininet
from mininet.node import Controller, RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.topo import Topo
from mininet.cli import CLI
from mininet import log
import requests

@dataclass(frozen=True)
class LinkWithParameters():
    link_info_key: int
    # switch_1
    # switch_2
    bw: int # in Mbps
    delay: str # formato "<numero decimale>ms"


class TestTopology(Topo):
    """Topologia di test per il progetto."""

    def build(self):
        h1, h2 = self.addHost('h1'), self.addHost('h2')
        s1 = self.addSwitch('s1')

        self.addLink(h1, s1)
        self.addLink(s1, h2)


class ProjectTopology(Topo):
    """Topologia assegnata per il progetto da realizzare."""
    def __init__(self, *args, **params):
        self.host_list: List[str] = []
        self.switch_list: List[str] = []
        self.link_list: List[LinkWithParameters] = []

        super().__init__(*args, **params)

    def build(self):
        # Funzione helper per popolare self.link_list
        def _helper_aggiungi_link(node1, node2, bw: int, delay: str):
            self.link_list.append(
                LinkWithParameters(
                    link_info_key=self.addLink(node1, node2, bw=bw, delay=delay),
                    bw=bw,
                    delay=delay,
                )
            )

        # Subnet 1
        h1 = self.addHost('h1', ip='10.0.0.1/24', defaultRoute='via 10.0.0.254')
        h2 = self.addHost('h2', ip='10.0.0.2/24', defaultRoute='via 10.0.0.254')
        sw1 = self.addSwitch('sw1')
        for host in (h1, h2):
            _helper_aggiungi_link(host, sw1, bw=100, delay='0.05ms')

        # Subnet 2
        h3 = self.addHost('h3', ip='11.0.0.1/24', defaultRoute='via 11.0.0.254')
        sw2 = self.addSwitch('sw2')
        _helper_aggiungi_link(h3, sw2, bw=1, delay='0.5ms')

        # Subnet 3
        h4 = self.addHost('h4', ip='192.168.1.1/24', defaultRoute='via 192.168.1.254')
        sw3 = self.addSwitch('sw3')
        _helper_aggiungi_link(h4, sw3, bw=100, delay='0.05ms')

        # Subnet 4
        h5 = self.addHost('h5', ip='10.8.1.1/24', defaultRoute='via 10.8.1.254')
        sw4 = self.addSwitch('sw4')
        _helper_aggiungi_link(h5, sw4, bw=100, delay='0.05ms')

        # Switch 5 interposto fra il 2 e 4
        sw5 = self.addSwitch('sw5')

        self.host_list.extend(tuple((h1, h2, h3, h4, h5)))
        self.switch_list.extend(tuple((sw1, sw2, sw3, sw4, sw5)))

        # Link per collegare i diversi switch fra di loro
        _helper_aggiungi_link(sw1, sw2, bw=20, delay='2ms')
        _helper_aggiungi_link(sw1, sw3, bw=1,  delay='2ms')
        _helper_aggiungi_link(sw2, sw5, bw=20, delay='2ms')
        _helper_aggiungi_link(sw3, sw4, bw=5,  delay='2ms')
        _helper_aggiungi_link(sw4, sw5, bw=20, delay='2ms')


    

# Mininet si aspetta che sia presente un dizionario `topos`
# nello scope globale del proprio file di configurazione,
# contenente tutte le topologie custom che si desidera utilizzare.
topos: Dict[str, Topo] = {
    "test": TestTopology,
    "project": ProjectTopology,
}

class MultiSwitch(OVSSwitch):
    """Una classe che connette ciascuno switch a più controller simultaneamente."""

    def start(self, controllers: List[Controller]):
        return OVSSwitch.start(self, controllers=controllers)

@dataclass(frozen=True)
class StaticRoute:
    destination: str
    gateway: str


@dataclass(frozen=True)
class SwitchConfig:
    id: int
    addresses: List[str] = field(default_factory=list)
    routes: List[StaticRoute] = field(default_factory=list)


def post_configs(endpoint: str, configs: List[SwitchConfig]):
    for switch in configs:
        id = switch.id

        for address in switch.addresses:
            requests.post(url=f"{endpoint}/router/{id:016}", json={"address": address})

        for route in switch.routes:
            requests.post(url=f"{endpoint}/router/{id:016}", json={
                "destination": route.destination,
                "gateway": route.gateway,
            })


def create_network():
    net = Mininet(topo=ProjectTopology(), switch=MultiSwitch, link=TCLink, autoSetMacs=True, controller=None, waitConnected=True)
    c0 = net.addController('c0', controller=RemoteController, port=6653)
    c1 = net.addController('c1', controller=RemoteController, port=6000)
    net.start()

    print(net.topo.host_list)
    print(net.topo.switch_list)
    print(net.topo.link_list)

    for switch_name in net.topo.switch_list:
        sw = net.get(f'{switch_name}')
        log.info(sw.cmd(f'ovs-vsctl set Bridge {switch_name} protocols=OpenFlow13'))

    switches_config = [
        SwitchConfig(
            id=1,
            addresses=["10.0.0.254/24", "180.0.0.1/30", "200.0.0.1/30"],
            # routes=[StaticRoute(destination="192.168.1.0/24", gateway="200.0.0.2")]
        ),
        SwitchConfig(id=2, addresses=["11.0.0.254/24", "180.0.0.2/30", "180.1.1.1/30"]),
        SwitchConfig(
            id=3,
            addresses=["192.168.1.254/24", "200.0.0.2/30", "170.0.0.1/30"],
            # routes=[StaticRoute(destination="10.0.0.0/24", gateway="200.0.0.1")],
        ),
        SwitchConfig(id=4, addresses=["10.8.1.254/24", "170.0.0.2/30", "180.1.2.1/30"]),
        SwitchConfig(id=5, addresses=["180.1.1.2/30", "180.1.2.2/30"]),
    ]

    post_configs(endpoint="http://localhost:8080", configs=switches_config)
    # risposta = chiamata_dijkstra(endpint="...", configs=richiesta)

    # chiamata_rotte_statiche_forse_con_post_configs(..., configs=riposta_PROCESSATA*)


    CLI(net)
    net.stop()

if __name__ == '__main__':
    log.setLogLevel('info')
    create_network()
