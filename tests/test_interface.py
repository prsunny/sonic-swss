from swsscommon import swsscommon

import time
import json

class TestRouterInterfaceIpv4(object):
    def setup_db(self, dvs):
        self.pdb = swsscommon.DBConnector(0, dvs.redis_sock, 0)
        self.adb = swsscommon.DBConnector(1, dvs.redis_sock, 0)
        self.cdb = swsscommon.DBConnector(4, dvs.redis_sock, 0)

    def add_ip_address(self, interface, ip):
        tbl = swsscommon.Table(self.cdb, "INTERFACE")
        fvs = swsscommon.FieldValuePairs([("NULL", "NULL")])
        tbl.set(interface + "|" + ip, fvs)
        time.sleep(1)

    def remove_ip_address(self, interface, ip):
        tbl = swsscommon.Table(self.cdb, "INTERFACE")
        tbl._del(interface + "|" + ip);
        time.sleep(1)

    def set_mtu(self, interface, mtu):
        tbl = swsscommon.Table(self.cdb, "PORT")
        fvs = swsscommon.FieldValuePairs([("mtu", mtu)])
        tbl.set(interface, fvs)
        time.sleep(1)

    def test_InterfaceAddRemoveIpv4Address(self, dvs):
        self.setup_db(dvs)

        # assign IP to interface
        self.add_ip_address("Ethernet8", "10.0.0.4/31")

        # check application database
        tbl = swsscommon.Table(self.pdb, "INTF_TABLE:Ethernet8")
        intf_entries = tbl.getKeys()
        assert len(intf_entries) == 1
        assert intf_entries[0] == "10.0.0.4/31"

        (status, fvs) = tbl.get(tbl.getKeys()[0])
        assert status == True
        assert len(fvs) == 2
        for fv in fvs:
            if fv[0] == "scope":
                assert fv[1] == "global"
            elif fv[0] == "family":
                assert fv[1] == "IPv4"
            else:
                assert False

        # check ASIC router interface database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ROUTER_INTERFACE")
        intf_entries = tbl.getKeys()
        # one loopback router interface one port based router interface
        assert len(intf_entries) == 2

        for key in intf_entries:
            (status, fvs) = tbl.get(key)
            assert status == True
            # a port based router interface has five field/value tuples
            if len(fvs) == 5:
                for fv in fvs:
                    if fv[0] == "SAI_ROUTER_INTERFACE_ATTR_TYPE":
                        assert fv[1] == "SAI_ROUTER_INTERFACE_TYPE_PORT"
                    # the default MTU without any configuration is 9100
                    if fv[0] == "SAI_ROUTER_INTERFACE_ATTR_MTU":
                        assert fv[1] == "9100"

        # check ASIC route database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ROUTE_ENTRY")
        for key in tbl.getKeys():
            route = json.loads(key)
            if route["dest"] == "10.0.0.4/31":
                subnet_found = True
            if route["dest"] == "10.0.0.4/32":
                ip2me_found = True

        assert subnet_found and ip2me_found

        # remove IP from interface
        self.remove_ip_address("Ethernet8", "10.0.0.4/31")

        # check application database
        tbl = swsscommon.Table(self.pdb, "INTF_TABLE:Ethernet8")
        intf_entries = tbl.getKeys()
        assert len(intf_entries) == 0

        # check ASIC database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ROUTE_ENTRY")
        for key in tbl.getKeys():
            route = json.loads(key)
            if route["dest"] == "10.0.0.4/31":
                assert False
            if route["dest"] == "10.0.0.4/32":
                assert False

    def test_InterfaceSetMtu(self, dvs):
        self.setup_db(dvs)

        # assign IP to interface
        self.add_ip_address("Ethernet16", "20.0.0.8/29")

        # configure MTU to interface
        self.set_mtu("Ethernet16", "8888")

        # check ASIC router interface database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ROUTER_INTERFACE")
        intf_entries = tbl.getKeys()
        # one loopback router interface one port based router interface
        assert len(intf_entries) == 2

        for key in intf_entries:
            (status, fvs) = tbl.get(key)
            assert status == True
            # a port based router interface has five field/value tuples
            if len(fvs) == 5:
                for fv in fvs:
                    if fv[0] == "SAI_ROUTER_INTERFACE_ATTR_TYPE":
                        assert fv[1] == "SAI_ROUTER_INTERFACE_TYPE_PORT"
                    # assert the new value set to the router interface
                    if fv[0] == "SAI_ROUTER_INTERFACE_ATTR_MTU":
                        assert fv[1] == "8888"

        # remove IP from interface
        self.remove_ip_address("Ethernet16", "20.0.0.8/29")

class TestLagRouterInterfaceIpv4(object):
    def setup_db(self, dvs):
        self.pdb = swsscommon.DBConnector(0, dvs.redis_sock, 0)
        self.adb = swsscommon.DBConnector(1, dvs.redis_sock, 0)
        self.cdb = swsscommon.DBConnector(4, dvs.redis_sock, 0)

    # TODO: below three functions will be replaced with configuration
    # database updates after the future changes of the lagmgrd
    def create_port_channel(self, dvs, interface):
        dvs.runcmd("teamd -d -t" + interface)
        time.sleep(1)

    def remove_port_channel(self, dvs, interface):
        dvs.runcmd("teamd -k -t" + interface)
        time.sleep(1)

    def add_port_channel_members(self, dvs, interface, members):
        for member in members:
            dvs.runcmd("ip link set dev " + interface + " up")
            dvs.runcmd("ip link set dev " + interface + " down")
            dvs.runcmd("teamdctl " + interface + " port add " + member)
        tbl = swsscommon.Table(self.cdb, "PORTCHANNEL")
        fvs = swsscommon.FieldValuePairs([("members@", ",".join(members))])
        tbl.set(interface, fvs)
        time.sleep(1)

    def add_ip_address(self, interface, ip):
        tbl = swsscommon.Table(self.cdb, "PORTCHANNEL_INTERFACE")
        fvs = swsscommon.FieldValuePairs([("NULL", "NULL")])
        tbl.set(interface + "|" + ip, fvs)
        time.sleep(1)

    def remove_ip_address(self, interface, ip):
        tbl = swsscommon.Table(self.cdb, "PORTCHANNEL_INTERFACE")
        tbl._del(interface + "|" + ip);
        time.sleep(1)

    def set_mtu(self, interface, mtu):
        tbl = swsscommon.Table(self.cdb, "PORTCHANNEL")
        fvs = swsscommon.FieldValuePairs([("mtu", mtu)])
        tbl.set(interface, fvs)
        time.sleep(1)

    def test_InterfaceAddRemoveIpv4Address(self, dvs):
        self.setup_db(dvs)

        # create port channel
        self.create_port_channel(dvs, "PortChannel001")

        # assign IP to interface
        self.add_ip_address("PortChannel001", "30.0.0.4/31")

        # check application database
        tbl = swsscommon.Table(self.pdb, "INTF_TABLE:PortChannel001")
        intf_entries = tbl.getKeys()
        assert len(intf_entries) == 1
        assert intf_entries[0] == "30.0.0.4/31"

        (status, fvs) = tbl.get(tbl.getKeys()[0])
        assert status == True
        assert len(fvs) == 2
        for fv in fvs:
            if fv[0] == "scope":
                assert fv[1] == "global"
            elif fv[0] == "family":
                assert fv[1] == "IPv4"
            else:
                assert False

        # check ASIC router interface database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ROUTER_INTERFACE")
        intf_entries = tbl.getKeys()
        # one loopback router interface one port based router interface
        assert len(intf_entries) == 2

        for key in intf_entries:
            (status, fvs) = tbl.get(key)
            assert status == True
            # a port based router interface has five field/value tuples
            if len(fvs) == 5:
                for fv in fvs:
                    if fv[0] == "SAI_ROUTER_INTERFACE_ATTR_TYPE":
                        assert fv[1] == "SAI_ROUTER_INTERFACE_TYPE_PORT"
                    # the default MTU without any configuration is 9100
                    if fv[0] == "SAI_ROUTER_INTERFACE_ATTR_MTU":
                        assert fv[1] == "9100"

        # check ASIC route database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ROUTE_ENTRY")
        for key in tbl.getKeys():
            route = json.loads(key)
            if route["dest"] == "30.0.0.4/31":
                subnet_found = True
            if route["dest"] == "30.0.0.4/32":
                ip2me_found = True

        assert subnet_found and ip2me_found

        # remove IP from interface
        self.remove_ip_address("PortChannel001", "30.0.0.4/31")

        # check application database
        tbl = swsscommon.Table(self.pdb, "INTF_TABLE:PortChannel001")
        intf_entries = tbl.getKeys()
        assert len(intf_entries) == 0

        # check ASIC database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ROUTE_ENTRY")
        for key in tbl.getKeys():
            route = json.loads(key)
            if route["dest"] == "30.0.0.4/31":
                assert False
            if route["dest"] == "30.0.0.4/32":
                assert False

        # remove port channel
        self.remove_port_channel(dvs, "PortChannel001")


    def test_InterfaceSetMtu(self, dvs):
        self.setup_db(dvs)

        # create port channel
        self.create_port_channel(dvs, "PortChannel002")

        # add port channel members
        self.add_port_channel_members(dvs, "PortChannel002", ["Ethernet0", "Ethernet4"])

        # assign IP to interface
        self.add_ip_address("PortChannel002", "40.0.0.8/29")

        # configure MTU to interface
        self.set_mtu("PortChannel002", "8888")

        # check ASIC router interface database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ROUTER_INTERFACE")
        intf_entries = tbl.getKeys()
        # one loopback router interface one port based router interface
        assert len(intf_entries) == 2

        for key in intf_entries:
            (status, fvs) = tbl.get(key)
            assert status == True
            # a port based router interface has five field/value tuples
            if len(fvs) == 5:
                for fv in fvs:
                    if fv[0] == "SAI_ROUTER_INTERFACE_ATTR_TYPE":
                        assert fv[1] == "SAI_ROUTER_INTERFACE_TYPE_PORT"
                    # assert the new value set to the router interface
                    if fv[0] == "SAI_ROUTER_INTERFACE_ATTR_MTU":
                        assert fv[1] == "8888"

        # check ASIC port database
        tbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_PORT")
        port_entries = tbl.getKeys()

        for key in port_entries:
            (status, fvs) = tbl.get(key)
            assert status == True
            # a member port configured with MTU will have six field/value tuples
            if len(fvs) == 6:
                for fv in fvs:
                    # asser the new value 8888 + 22 = 8910 set to the port
                    if fv[0] == "SAI_PORT_ATTR_MTU":
                        assert fv[1] == "8910"

        # remove IP from interface
        self.remove_ip_address("Ethernet16", "40.0.0.8/29")

        # remove port channel
        self.remove_port_channel(dvs, "PortChannel002")
