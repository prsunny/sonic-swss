#pragma once

#include <map>
#include <set>
#include <memory>
#include "request_parser.h"
#include "portsorch.h"
#include "vrforch.h"

enum class map_type
{
    MAP_TYPE_INVALID,
    VNI_TO_VLAN_ID,
    VLAN_ID_TO_VNI,
    VRID_TO_VNI,
    VNI_TO_VRID
};

struct tunnel_ids_t
{
    sai_object_id_t tunnel_encap_id;
    sai_object_id_t tunnel_decap_id;
    sai_object_id_t tunnel_id;
    sai_object_id_t tunnel_term_id;
};

class VxlanTunnel
{
public:
    VxlanTunnel(string name, IpAddress src_ip, IpAddress dst_ip)
                :tunnel_name(name), src_ip(src_ip), dst_ip(dst_ip) { }

    bool isActive() const
    {
        return active;
    }

    bool createTunnel(map_type encap, map_type decap);
    sai_object_id_t addEncapMapperEntry(sai_object_id_t vrf, uint32_t vni);
    sai_object_id_t addDecapMapperEntry(sai_object_id_t vrf, uint32_t vni);

    sai_object_id_t getDecapMapId(const std::string& tunnel_name) const
    {
        return ids.tunnel_decap_id;
    }

    sai_object_id_t getEncapMapId(const std::string& tunnel_name) const
    {
        return ids.tunnel_encap_id;
    }

private:
    string tunnel_name;

    bool active = false;

    tunnel_ids_t ids = {0x0, 0x0, 0x0, 0x0};

    IpAddress       src_ip;
    IpAddress       dst_ip = 0x0;
};

const request_description_t vxlan_tunnel_request_description = {
            { REQ_T_STRING },
            {
                { "src_ip", REQ_T_IP },
                { "dst_ip", REQ_T_IP },
            },
            { "src_ip" }
};

class VxlanTunnelRequest : public Request
{
public:
    VxlanTunnelRequest() : Request(vxlan_tunnel_request_description, '|') { }
};

using VxlanTunnel_T = std::unique_ptr<VxlanTunnel>;
typedef std::map<std::string, VxlanTunnel_T> VxlanTunnelTable;

class VxlanTunnelOrch : public Orch2
{
public:
    VxlanTunnelOrch(DBConnector *db, const std::string& tableName) : Orch2(db, tableName, request_) { }

    bool isTunnelExists(const std::string& tunnel_name) const
    {
        return vxlan_tunnel_table_.find(tunnel_name) != std::end(vxlan_tunnel_table_);
    }

    VxlanTunnel_T& getVxlanTunnel(const std::string& tunnel_name)
    {
        return vxlan_tunnel_table_.at(tunnel_name);
    }

private:
    virtual bool addOperation(const Request& request);
    virtual bool delOperation(const Request& request);

    VxlanTunnelTable vxlan_tunnel_table_;
    VxlanTunnelRequest request_;
};

const request_description_t vxlan_tunnel_map_request_description = {
            { REQ_T_STRING, REQ_T_STRING },
            {
                { "vni",  REQ_T_UINT },
                { "vlan", REQ_T_VLAN },
            },
            { "vni", "vlan" }
};

typedef std::map<std::string, sai_object_id_t> VxlanTunnelMapTable;

class VxlanTunnelMapRequest : public Request
{
public:
    VxlanTunnelMapRequest() : Request(vxlan_tunnel_map_request_description, '|') { }
};

class VxlanTunnelMapOrch : public Orch2
{
public:
    VxlanTunnelMapOrch(DBConnector *db, const std::string& tableName) : Orch2(db, tableName, request_) { }

    bool isTunnelMapExists(const std::string& name) const
    {
        return vxlan_tunnel_map_table_.find(name) != std::end(vxlan_tunnel_map_table_);
    }
private:
    virtual bool addOperation(const Request& request);
    virtual bool delOperation(const Request& request);

    VxlanTunnelMapTable vxlan_tunnel_map_table_;
    VxlanTunnelMapRequest request_;
};

const request_description_t vxlan_vnet_request_description = {
            { REQ_T_STRING },
            {
                { "vxlan_tunnel", REQ_T_STRING },
                { "vni", REQ_T_UINT },
                { "peer_list", REQ_T_SET },
            },
            { "vxlan_tunnel", "vni" }
};

class VxlanVnetRequest : public Request
{
public:
    VxlanVnetRequest() : Request(vxlan_vnet_request_description, '|') { }
};

struct vnet_entry_t {
    string tunnel_name;
    uint32_t vni;
    std::set<string> peer_list;
};

typedef std::map<string, vnet_entry_t> VxlanVnetTable;

class VxlanVnetOrch : public Orch2
{
public:
    VxlanVnetOrch(DBConnector *db, const std::string& tableName) : Orch2(db, tableName, request_) { }

    bool isVnetExists(const std::string& name) const
    {
        return vxlan_vnet_table_.find(name) != std::end(vxlan_vnet_table_);
    }

private:
    virtual bool addOperation(const Request& request);
    virtual bool delOperation(const Request& request);

    VxlanVnetTable vxlan_vnet_table_;
    VxlanVnetRequest request_;
};

/*
 * FIXME - This must be handled by IntfMgrD
 */
const request_description_t vnet_intf_request_description = {
            { REQ_T_STRING, REQ_T_IP },
            {
                { "vnet_name", REQ_T_STRING },
            },
            { "vnet_name" }
};

class VnetIntfRequest : public Request
{
public:
    VnetIntfRequest() : Request(vnet_intf_request_description, '|') { }
};

class VnetIntfOrch : public Orch2
{
public:
    VnetIntfOrch(DBConnector *db, const std::string& tableName) : Orch2(db, tableName, request_) { }

private:
    virtual bool addOperation(const Request& request);
    virtual bool delOperation(const Request& request);


    VnetIntfRequest request_;
};
