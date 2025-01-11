from dataclasses import dataclass, field
from typing import List, Dict

from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.link import TCLink
from mininet.topo import Topo
from mininet.cli import CLI
from mininet import log
import requests

class TestTopology(Topo):
    """Topologia di test per il progetto."""

    def build(self):
        h1, h2 = self.addHost('h1'), self.addHost('h2')
        s1 = self.addSwitch('s1')

        self.addLink(h1, s1)
        self.addLink(s1, h2)


class ProjectTopology(Topo):
    """Topologia assegnata per il progetto da realizzare."""

    def build(self):
        # Subnet 1
        h1 = self.addHost('h1', ip='10.0.0.1/24', defaultRoute='via 10.0.0.254')
        h2 = self.addHost('h2', ip='10.0.0.2/24', defaultRoute='via 10.0.0.254')
        sw1 = self.addSwitch('sw1')
        for host in (h1, h2):
            self.addLink(host, sw1, bw=100, delay='0.05ms')

        # Subnet 2
        h3 = self.addHost('h3', ip='11.0.0.1/24', defaultRoute='via 11.0.0.254')
        sw2 = self.addSwitch('sw2')
        self.addLink(h3, sw2, bw=1, delay='0.5ms')

        # Subnet 3
        h4 = self.addHost('h4', ip='192.168.1.1/24', defaultRoute='via 192.168.1.254')
        sw3 = self.addSwitch('sw3')
        self.addLink(h4, sw3, bw=100, delay='0.05ms')

        # Subnet 4
        h5 = self.addHost('h5', ip='10.8.1.1/24', defaultRoute='via 10.8.1.254')
        sw4 = self.addSwitch('sw4')
        self.addLink(h5, sw4, bw=100, delay='0.05ms')

        # Switch 5 interposto fra il 2 e 4
        sw5 = self.addSwitch('sw5')

        # Link per collegare i diversi switch fra di loro
        self.addLink(sw1, sw2, bw=20, delay='2ms')
        self.addLink(sw1, sw3, bw=1,  delay='2ms')
        self.addLink(sw2, sw5, bw=20, delay='2ms')
        self.addLink(sw3, sw4, bw=5,  delay='2ms')
        self.addLink(sw4, sw5, bw=20, delay='2ms')
    

# Mininet si aspetta che sia presente un dizionario `topos`
# nello scope globale del proprio file di configurazione,
# contenente tutte le topologie custom che si desidera utilizzare.
topos: Dict[str, Topo] = {
    "test": TestTopology,
    "project": ProjectTopology,
}

@dataclass(frozen=True)
class SwitchConfig:
    id: int
    addresses: List[str] = field(default_factory=list)

    def yield_addresses(self):
        yield from self.addresses


def post_configs(endpoint: str, configs: List[SwitchConfig]):
    for switch in configs:
        id = switch.id
        for address in switch.yield_addresses():
            requests.post(url=f"{endpoint}/router/{id:016}", json={"address": address})


def create_network():
    net = Mininet(topo=ProjectTopology(), switch=OVSKernelSwitch, link=TCLink, autoSetMacs=True, controller=RemoteController, waitConnected=True)
    net.start()

    for switch_id in range(1, 5+1):
        sw = net.get(f'sw{switch_id}')
        log.info(sw.cmd(f'ovs-vsctl set Bridge sw{switch_id} protocols=OpenFlow13'))

    switches_config = [
        SwitchConfig(id=1, addresses=["10.0.0.254/24", "180.0.0.1/30", "200.0.0.1/30"]),
        SwitchConfig(id=2, addresses=["11.0.0.254/24", "180.0.0.2/30", "180.1.1.1/30"]),
        SwitchConfig(id=3, addresses=["192.168.1.254/24", "200.0.0.2/30", "170.0.0.1/30"]),
        SwitchConfig(id=4, addresses=["10.8.1.254/24", "170.0.0.2/30", "180.1.2.1/30"]),
        SwitchConfig(id=5, addresses=["180.1.1.2/30", "180.1.2.2/30"]),
    ]
    post_configs(endpoint="http://localhost:8080", configs=switches_config)

    CLI(net)
    net.stop()

if __name__ == '__main__':
    log.setLogLevel('info')
    create_network()
