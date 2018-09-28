import os
import os.path
import re
import time
import json
import redis
import docker
import pytest
import commands
import tarfile
import StringIO
import subprocess
from swsscommon import swsscommon

def ensure_system(cmd):
    rc = os.WEXITSTATUS(os.system(cmd))
    if rc:
        raise RuntimeError('Failed to run command: %s' % cmd)

def pytest_addoption(parser):
    parser.addoption("--dvsname", action="store", default=None,
                      help="dvs name")

class AsicDbValidator(object):
    def __init__(self, dvs):
        self.adb = swsscommon.DBConnector(1, dvs.redis_sock, 0)

        # get default dot1q vlan id
        atbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_VLAN")

        keys = atbl.getKeys()
        assert len(keys) == 1
        self.default_vlan_id = keys[0]

        # build port oid to front port name mapping
        self.portoidmap = {}
        self.portnamemap = {}
        self.hostifoidmap = {}
        self.hostifnamemap = {}
        atbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_HOSTIF")
        keys = atbl.getKeys()

        assert len(keys) == 32
        for k in keys:
            (status, fvs) = atbl.get(k)

            assert status == True

            for fv in fvs:
                if fv[0] == "SAI_HOSTIF_ATTR_OBJ_ID":
                    port_oid = fv[1]
                elif fv[0] == "SAI_HOSTIF_ATTR_NAME":
                    port_name = fv[1]

            self.portoidmap[port_oid] = port_name
            self.portnamemap[port_name] = port_oid
            self.hostifoidmap[k] = port_name
            self.hostifnamemap[port_name] = k

        # get default acl table and acl rules
        atbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_TABLE")
        keys = atbl.getKeys()

        assert len(keys) >= 1
        self.default_acl_tables = keys

        atbl = swsscommon.Table(self.adb, "ASIC_STATE:SAI_OBJECT_TYPE_ACL_ENTRY")
        keys = atbl.getKeys()

        assert len(keys) == 2
        self.default_acl_entries = keys

class ApplDbValidator(object):
    def __init__(self, dvs):
        appl_db = swsscommon.DBConnector(swsscommon.APPL_DB, dvs.redis_sock, 0)
        self.neighTbl = swsscommon.Table(appl_db, "NEIGH_TABLE")

    def __del__(self):
        # Make sure no neighbors on vEthernet
        keys = self.neighTbl.getKeys();
        for key in keys:
            assert not key.startswith("vEthernet")

class VirtualServer(object):
    def __init__(self, ctn_name, pid, i):
        self.nsname = "%s-srv%d" % (ctn_name, i)
        self.vifname = "vEthernet%d" % (i * 4)
        self.cleanup = True

        # create netns
        if os.path.exists("/var/run/netns/%s" % self.nsname):
            self.cleanup = False
        else:
            ensure_system("ip netns add %s" % self.nsname)

            # create vpeer link
            ensure_system("ip link add %s type veth peer name %s" % (self.nsname[0:12], self.vifname))
            ensure_system("ip link set %s netns %s" % (self.nsname[0:12], self.nsname))
            ensure_system("ip link set %s netns %d" % (self.vifname, pid))

            # bring up link in the virtual server
            ensure_system("ip netns exec %s ip link set dev %s name eth0" % (self.nsname, self.nsname[0:12]))
            ensure_system("ip netns exec %s ip link set dev eth0 up" % (self.nsname))
            ensure_system("ip netns exec %s ethtool -K eth0 tx off" % (self.nsname))

            # bring up link in the virtual switch
            ensure_system("nsenter -t %d -n ip link set dev %s up" % (pid, self.vifname))

            # disable arp, so no neigh on vEthernet(s)
            ensure_system("nsenter -t %d -n ip link set arp off dev %s" % (pid, self.vifname))

    def __del__(self):
        if self.cleanup:
            pids = subprocess.check_output("ip netns pids %s" % (self.nsname), shell=True)
            if pids:
                for pid in pids.split('\n'):
                    if len(pid) > 0:
                        os.system("kill %s" % int(pid))
            os.system("ip netns delete %s" % self.nsname)

    def runcmd(self, cmd):
        return os.system("ip netns exec %s %s" % (self.nsname, cmd))

    def runcmd_async(self, cmd):
        return subprocess.Popen("ip netns exec %s %s" % (self.nsname, cmd), shell=True)

class DockerVirtualSwitch(object):
    def __init__(self, name=None):
        self.pnames = ['fpmsyncd',
                       'intfmgrd',
                       'intfsyncd',
                       'neighsyncd',
                       'orchagent',
                       'portsyncd',
                       'redis-server',
                       'rsyslogd',
                       'syncd',
                       'teamsyncd',
                       'vlanmgrd',
                       'zebra']
        self.mount = "/var/run/redis-vs"
        self.redis_sock = self.mount + '/' + "redis.sock"
        self.client = docker.from_env()

        self.ctn = None
        self.cleanup = True
        if name != None:
            # get virtual switch container
            for ctn in self.client.containers.list():
                if ctn.name == name:
                    self.ctn = ctn
                    (status, output) = commands.getstatusoutput("docker inspect --format '{{.HostConfig.NetworkMode}}' %s" % name)
                    ctn_sw_id = output.split(':')[1]
                    self.cleanup = False
            if self.ctn == None:
                raise NameError("cannot find container %s" % name)

            # get base container
            for ctn in self.client.containers.list():
                if ctn.id == ctn_sw_id or ctn.name == ctn_sw_id:
                    ctn_sw_name = ctn.name

            (status, output) = commands.getstatusoutput("docker inspect --format '{{.State.Pid}}' %s" % ctn_sw_name)
            self.ctn_sw_pid = int(output)

            # create virtual servers
            self.servers = []
            for i in range(32):
                server = VirtualServer(ctn_sw_name, self.ctn_sw_pid, i)
                self.servers.append(server)

            self.restart()
        else:
            self.ctn_sw = self.client.containers.run('debian:jessie', privileged=True, detach=True,
                    command="bash", stdin_open=True)
            (status, output) = commands.getstatusoutput("docker inspect --format '{{.State.Pid}}' %s" % self.ctn_sw.name)
            self.ctn_sw_pid = int(output)

            # create virtual server
            self.servers = []
            for i in range(32):
                server = VirtualServer(self.ctn_sw.name, self.ctn_sw_pid, i)
                self.servers.append(server)

            # create virtual switch container
            self.ctn = self.client.containers.run('docker-sonic-vs', privileged=True, detach=True,
                    network_mode="container:%s" % self.ctn_sw.name,
                    volumes={ self.mount: { 'bind': '/var/run/redis', 'mode': 'rw' } })

        self.appldb = None
        try:
            self.ctn.exec_run("sysctl -w net.ipv6.conf.all.disable_ipv6=0")
            self.check_ready()
            self.init_asicdb_validator()
            self.appldb = ApplDbValidator(self)
        except:
            self.destroy()
            raise

    def destroy(self):
        if self.appldb:
            del self.appldb
        if self.cleanup:
            self.ctn.remove(force=True)
            self.ctn_sw.remove(force=True)
            for s in self.servers:
                del(s)

    def check_ready(self, timeout=30):
        '''check if all processes in the dvs is ready'''

        re_space = re.compile('\s+')
        process_status = {}
        ready = False
        started = 0
        while True:
            # get process status
            res = self.ctn.exec_run("supervisorctl status")
            try:
                out = res.output
            except AttributeError:
                out = res
            for l in out.split('\n'):
                fds = re_space.split(l)
                if len(fds) < 2:
                    continue
                process_status[fds[0]] = fds[1]

            # check if all processes are running
            ready = True
            for pname in self.pnames:
                try:
                    if process_status[pname] != "RUNNING":
                        ready = False
                except KeyError:
                    ready = False

            if ready == True:
                break

            started += 1
            if started > timeout:
                raise ValueError(out)

            time.sleep(1)

    def restart(self):
        self.ctn.restart()

    def init_asicdb_validator(self):
        self.asicdb = AsicDbValidator(self)

    def runcmd(self, cmd):
        res = self.ctn.exec_run(cmd)
        try:
            exitcode = res.exit_code
            out = res.output
        except AttributeError:
            exitcode = 0
            out = res
        return (exitcode, out)

    def copy_file(self, path, filename):
        tarstr = StringIO.StringIO()
        tar = tarfile.open(fileobj=tarstr, mode="w")
        tar.add(filename, os.path.basename(filename))
        tar.close()
        self.ctn.exec_run("mkdir -p %s" % path)
        self.ctn.put_archive(path, tarstr.getvalue())
        tarstr.close()

    def get_map_iface_bridge_port_id(self, asic_db):
        port_id_2_iface = self.asicdb.portoidmap
        tbl = swsscommon.Table(asic_db, "ASIC_STATE:SAI_OBJECT_TYPE_BRIDGE_PORT")
        iface_2_bridge_port_id = {}
        for key in tbl.getKeys():
            status, data = tbl.get(key)
            assert status
            values = dict(data)
            iface_id = values["SAI_BRIDGE_PORT_ATTR_PORT_ID"]
            iface_name = port_id_2_iface[iface_id]
            iface_2_bridge_port_id[iface_name] = key

        return iface_2_bridge_port_id

    def is_table_entry_exists(self, db, table, keyregex, attributes):
        tbl = swsscommon.Table(db, table)
        keys = tbl.getKeys()

        extra_info = []
        for key in keys:
            if re.match(keyregex, key) is None:
                continue

            status, fvs = tbl.get(key)
            assert status, "Error reading from table %s" % table

            d_attributes = dict(attributes)
            for k, v in fvs:
                if k in d_attributes and d_attributes[k] == v:
                    del d_attributes[k]

            if len(d_attributes) != 0:
                extra_info.append("Desired attributes %s was not found for key %s" % (str(d_attributes), key))
            else:
                return True, extra_info
        else:
            if not extra_info:
                extra_info.append("Desired key regex %s was not found" % str(keyregex))
            return False, extra_info

    def is_fdb_entry_exists(self, db, table, key_values, attributes):
        tbl =  swsscommon.Table(db, table)
        keys = tbl.getKeys()

        exists = False
        extra_info = []
        key_found = False
        for key in keys:
            try:
                d_key = json.loads(key)
            except ValueError:
                d_key = json.loads('{' + key + '}')

            for k, v in key_values:
                if k not in d_key or v != d_key[k]:
                    continue

            key_found = True

            status, fvs = tbl.get(key)
            assert status, "Error reading from table %s" % table

            d_attributes = dict(attributes)
            for k, v in fvs:
                if k in d_attributes and d_attributes[k] == v:
                    del d_attributes[k]

            if len(d_attributes) != 0:
                exists = False
                extra_info.append("Desired attributes %s was not found for key %s" % (str(d_attributes), key))
            else:
                exists = True
                break

        if not key_found:
            exists = False
            extra_info.append("Desired key with parameters %s was not found" % str(key_values))

        return exists, extra_info

    def create_vlan(self, vlan):
        tbl = swsscommon.Table(self.cdb, "VLAN")
        fvs = swsscommon.FieldValuePairs([("vlanid", vlan)])
        tbl.set("Vlan" + vlan, fvs)
        time.sleep(1)

    def create_vlan_member(self, vlan, interface):
        tbl = swsscommon.Table(self.cdb, "VLAN_MEMBER")
        fvs = swsscommon.FieldValuePairs([("tagging_mode", "untagged")])
        tbl.set("Vlan" + vlan + "|" + interface, fvs)
        time.sleep(1)

    def set_interface_status(self, interface, admin_status):
        if interface.startswith("PortChannel"):
            tbl_name = "PORTCHANNEL"
        elif interface.startswith("Vlan"):
            tbl_name = "VLAN"
        else:
            tbl_name = "PORT"
        tbl = swsscommon.Table(self.cdb, tbl_name)
        fvs = swsscommon.FieldValuePairs([("admin_status", "up")])
        tbl.set(interface, fvs)
        time.sleep(1)

    def add_ip_address(self, interface, ip):
        if interface.startswith("PortChannel"):
            tbl_name = "PORTCHANNEL_INTERFACE"
        elif interface.startswith("Vlan"):
            tbl_name = "VLAN_INTERFACE"
        else:
            tbl_name = "INTERFACE"
        tbl = swsscommon.Table(self.cdb, tbl_name)
        fvs = swsscommon.FieldValuePairs([("NULL", "NULL")])
        tbl.set(interface + "|" + ip, fvs)
        time.sleep(1)

    def add_neighbor(self, interface, ip, mac):
        tbl = swsscommon.ProducerStateTable(self.pdb, "NEIGH_TABLE")
        fvs = swsscommon.FieldValuePairs([("neigh", mac),
                                          ("family", "IPv4")])
        tbl.set(interface + ":" + ip, fvs)
        time.sleep(1)

    def setup_db(self):
        self.pdb = swsscommon.DBConnector(0, self.redis_sock, 0)
        self.adb = swsscommon.DBConnector(1, self.redis_sock, 0)
        self.cdb = swsscommon.DBConnector(4, self.redis_sock, 0)
        self.sdb = swsscommon.DBConnector(6, self.redis_sock, 0)

    def getCrmCounterValue(self, key, counter):
        counters_db = swsscommon.DBConnector(swsscommon.COUNTERS_DB, self.redis_sock, 0)
        crm_stats_table = swsscommon.Table(counters_db, 'CRM')

        for k in crm_stats_table.get(key)[1]:
            if k[0] == counter:
                return int(k[1])

    def setReadOnlyAttr(self, obj, attr, val):
        db = swsscommon.DBConnector(swsscommon.ASIC_DB, self.redis_sock, 0)
        tbl = swsscommon.Table(db, "ASIC_STATE:{0}".format(obj))
        keys = tbl.getKeys()

        assert len(keys) == 1

        swVid = keys[0]
        r = redis.Redis(unix_socket_path=self.redis_sock, db=swsscommon.ASIC_DB)
        swRid = r.hget("VIDTORID", swVid)

        assert swRid is not None

        ntf = swsscommon.NotificationProducer(db, "SAI_VS_UNITTEST_CHANNEL")
        fvp = swsscommon.FieldValuePairs()
        ntf.send("enable_unittests", "true", fvp)
        fvp = swsscommon.FieldValuePairs([(attr, val)])
        key = "SAI_OBJECT_TYPE_SWITCH:" + swRid

        ntf.send("set_ro", key, fvp)

    # start processes in SWSS
    def start_swss(self):
        self.runcmd(['sh', '-c', 'supervisorctl start orchagent; supervisorctl start portsyncd; supervisorctl start intfsyncd; \
            supervisorctl start neighsyncd; supervisorctl start intfmgrd; supervisorctl start vlanmgrd; \
            supervisorctl start buffermgrd; supervisorctl start arp_update'])

    # stop processes in SWSS
    def stop_swss(self):
        self.runcmd(['sh', '-c', 'supervisorctl stop orchagent; supervisorctl stop portsyncd; supervisorctl stop intfsyncd; \
            supervisorctl stop neighsyncd;  supervisorctl stop intfmgrd; supervisorctl stop vlanmgrd; \
            supervisorctl stop buffermgrd; supervisorctl stop arp_update'])

@pytest.yield_fixture(scope="module")
def dvs(request):
    name = request.config.getoption("--dvsname")
    dvs = DockerVirtualSwitch(name)
    yield dvs
    dvs.destroy()
