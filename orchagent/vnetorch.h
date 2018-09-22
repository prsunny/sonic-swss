#ifndef __VNETORCH_H
#define __VNETORCH_H

#include <vector>
#include <set>

#include "request_parser.h"

extern sai_object_id_t gVirtualRouterId;

const request_description_t vnet_request_description = {
    { REQ_T_STRING },
    {
        { "src_mac",       REQ_T_MAC_ADDRESS },
        { "vnet_name",     REQ_T_STRING },
        { "peer_list",     REQ_T_SET },
    },
    { } // no mandatory attributes
};

enum class VR_TYPE{
    ING_VR_VALID,
    EGR_VR_VALID,
    VR_INVALID
};

class VNetRequest : public Request
{
public:
    VNetRequest() : Request(vnet_request_description, ':') { }
};

class VNetObject
{
public:
    VNetObject(string vr_name, set<sai_object_id_t>& vr_ents, set<string>& p_list)
              :vrf_name(vr_name)
    {
        peer_list = p_list;
        vr_ids = vr_ents;
    }

    sai_object_id_t getVRFidIngress() const
    {
        return 0x0;
    }

    sai_object_id_t getVRFidEgress() const
    {
        return 0x0;
    }

    set<sai_object_id_t> getVRids() const
    {
        return vr_ids;
    }

    string getVRFname() const
    {
        return vrf_name;
    }

private:
    string vrf_name;
    set<string> peer_list = {};
    set<sai_object_id_t> vr_ids = {};
};

using VNetObject_T = std::unique_ptr<VNetObject>;
typedef std::unordered_map<std::string, VNetObject_T> VNetTable;
typedef std::unordered_map<std::string, std::string> VRFMapTable;

class VNetOrch : public Orch2
{
public:
    VNetOrch(DBConnector *db, const std::string& tableName) : Orch2(db, tableName, request_)
    {
        vr_cntxt = { VR_TYPE::ING_VR_VALID, VR_TYPE::EGR_VR_VALID };
    }

    bool isVnetexists(const std::string& name) const
    {
        return vnet_table_.find(name) != std::end(vnet_table_);
    }

    sai_object_id_t getVRFidIngress(const std::string& name) const
    {
        return vnet_table_.at(name)->getVRFidIngress();
    }

    sai_object_id_t getVRFidEgress(const std::string& name) const
    {
        return vnet_table_.at(name)->getVRFidEgress();
    }

    set<sai_object_id_t> getVRids(const std::string& name) const
    {
        return vnet_table_.at(name)->getVRids();
    }

    bool isVRFMapexists(const std::string& name) const
    {
        return map_table_.find(name) != std::end(map_table_);
    }

    string getVnetName(const std::string& vrf) const
    {
        return map_table_.at(vrf);
    }

private:
    virtual bool addOperation(const Request& request);
    virtual bool delOperation(const Request& request);

    VNetTable vnet_table_;
    VRFMapTable map_table_; //VRF to Vnet Map
    VNetRequest request_;

    std::vector<VR_TYPE> vr_cntxt;
};

#endif // __VNETORCH_H
