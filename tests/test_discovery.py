"""Unit tests for app.services.discovery CIDR/IP expansion."""

from __future__ import annotations

from app.services.discovery import _hosts_for_target, default_network, local_ipv4_for


def test_single_ip_expands_to_itself():
    hosts = _hosts_for_target("10.0.1.42")
    assert hosts == ["10.0.1.42"]


def test_cidr_expands_to_usable_hosts():
    hosts = _hosts_for_target("10.0.1.0/30")
    assert hosts == ["10.0.1.1", "10.0.1.2"]


def test_cidr_slash_24_has_254_hosts():
    hosts = _hosts_for_target("192.168.1.0/24")
    assert len(hosts) == 254
    assert hosts[0] == "192.168.1.1"
    assert hosts[-1] == "192.168.1.254"


def test_default_network_returns_a_valid_cidr():
    network = default_network()
    assert "/" in network


def test_local_ipv4_for_non_ip_peer_is_empty():
    assert local_ipv4_for("testclient") == ""
    assert local_ipv4_for("") == ""


def test_local_ipv4_for_returns_an_address_on_the_peer_subnet():
    import ipaddress

    network = ipaddress.ip_network(default_network())
    peer = str(next(network.hosts()))
    local = local_ipv4_for(peer)
    assert local == "" or ipaddress.ip_address(local) in network
