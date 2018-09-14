#ifndef __VRFORCH_H
#define __VRFORCH_H

#include "request_parser.h"

extern sai_object_id_t gVirtualRouterId;
typedef std::unordered_map<std::string, sai_object_id_t> VRFTable;

const request_description_t request_description = {
    { REQ_T_STRING },
    {
        { "v4",            REQ_T_BOOL },
        { "v6",            REQ_T_BOOL },
        { "src_mac",       REQ_T_MAC_ADDRESS },
        { "ttl_action",    REQ_T_PACKET_ACTION },
        { "ip_opt_action", REQ_T_PACKET_ACTION },
        { "l3_mc_action",  REQ_T_PACKET_ACTION },
        { "vnet_name",     REQ_T_STRING },
    },
    { } // no mandatory attributes
};

class VRFRequest : public Request
{
public:
    VRFRequest() : Request(request_description, ':') { }
};

struct VnetEntry
{
    std::string vrf_name;
    sai_object_id_t ing_vrf;
    sai_object_id_t egr_vrf;
};
typedef std::unordered_map<std::string, struct VnetEntry> VnetTable;


class VRFOrch : public Orch2
{
public:
    VRFOrch(DBConnector *db, const std::string& tableName) : Orch2(db, tableName, request_)
    {
    }

    bool isVRFexists(const std::string& name) const
    {
        return vrf_table_.find(name) != std::end(vrf_table_);
    }

    sai_object_id_t getVRFid(const std::string& name) const
    {
        if (vrf_table_.find(name) != std::end(vrf_table_))
        {
            return vrf_table_.at(name);
        }
        else
        {
            return gVirtualRouterId;
        }
    }

    bool isVnetexists(const std::string& name) const
    {
        return vnet_table_.find(name) != std::end(vnet_table_);
    }

    sai_object_id_t getVRFidIngress(const std::string& name) const
    {
        return vnet_table_.at(name).ing_vrf;
    }

    sai_object_id_t getVRFidEgress(const std::string& name) const
    {
        return vnet_table_.at(name).egr_vrf;
    }
private:
    virtual bool addOperation(const Request& request);
    virtual bool delOperation(const Request& request);

    VRFTable vrf_table_;
    VnetTable vnet_table_;
    VRFRequest request_;
};

#endif // __VRFORCH_H
