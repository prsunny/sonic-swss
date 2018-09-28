#ifndef __VNETORCH_H
#define __VNETORCH_H

#include <vector>
#include <set>
#include <unordered_map>
#include <algorithm>

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

enum class VNET_EXEC
{
    VNET_EXEC_VRF,
    VNET_EXEC_BRIDGE,
    VNET_EXEC_INVALID
};

enum class VR_TYPE
{
    ING_VR_VALID,
    EGR_VR_VALID,
    VR_INVALID
};

using vrid_list_t = map<VR_TYPE, sai_object_id_t>;

class VNetRequest : public Request
{
public:
    VNetRequest() : Request(vnet_request_description, ':') { }
};

class VNetObject
{
public:
    VNetObject(set<string>& p_list)
    {
        peer_list = p_list;
    }

    virtual sai_object_id_t getEncapMapId() const = 0;

    virtual sai_object_id_t getDecapMapId() const = 0;

    virtual ~VNetObject() {};

private:
    set<string> peer_list = {};
};

class VNetVrfObject : public VNetObject
{
public:
    VNetVrfObject(vrid_list_t& vr_ents, set<string>& p_list) : VNetObject(p_list)
    {
        vr_ids = vr_ents;
    }

    sai_object_id_t getVRidIngress() const
    {
        if (vr_ids.find(VR_TYPE::ING_VR_VALID) != vr_ids.end())
        {
            return vr_ids.at(VR_TYPE::ING_VR_VALID);
        }
        return 0x0;
    }

    sai_object_id_t getVRidEgress() const
    {
        if (vr_ids.find(VR_TYPE::EGR_VR_VALID) != vr_ids.end())
        {
            return vr_ids.at(VR_TYPE::EGR_VR_VALID);
        }
        return 0x0;
    }

    set<sai_object_id_t> getVRids() const
    {
        set<sai_object_id_t> ids;

        for_each (vr_ids.begin(), vr_ids.end(), [&](std::pair<VR_TYPE, sai_object_id_t> element)
        {
            ids.insert(element.second);
        });

        return ids;
    }

    virtual sai_object_id_t getEncapMapId() const
    {
        return getVRidIngress();
    }

    virtual sai_object_id_t getDecapMapId() const
    {
        return getVRidEgress();
    }

private:
    vrid_list_t vr_ids;
};

using VNetObject_T = std::unique_ptr<VNetObject>;
typedef std::unordered_map<std::string, VNetObject_T> VNetTable;

class VNetOrch : public Orch2
{
public:
    VNetOrch(DBConnector *db, const std::string& tableName, VNET_EXEC op = VNET_EXEC::VNET_EXEC_VRF)
             : Orch2(db, tableName, request_)
    {
        vnet_exec_ = op;

        if (op == VNET_EXEC::VNET_EXEC_VRF)
        {
            vr_cntxt = { VR_TYPE::ING_VR_VALID, VR_TYPE::EGR_VR_VALID };
        }
        else
        {
            //BRIDGE Implementation
        }
    }

    bool isVnetexists(const std::string& name) const
    {
        return vnet_table_.find(name) != std::end(vnet_table_);
    }

    VNetVrfObject* getVRptr(const std::string& name) const
    {
        return static_cast<VNetVrfObject *>(vnet_table_.at(name).get());
    }

    sai_object_id_t getEncapMapId(const std::string& name) const
    {
        return vnet_table_.at(name)->getEncapMapId();
    }

    sai_object_id_t getDecapMapId(const std::string& name) const
    {
        return vnet_table_.at(name)->getDecapMapId();
    }

    bool isVnetExecVrf() const
    {
        return (vnet_exec_ == VNET_EXEC::VNET_EXEC_VRF);
    }

    bool isVnetExecBridge() const
    {
        return (vnet_exec_ == VNET_EXEC::VNET_EXEC_BRIDGE);
    }

private:
    virtual bool addOperation(const Request& request);
    virtual bool delOperation(const Request& request);

    bool addOpVrf(const string&, set<string>&, vector<sai_attribute_t>&);
    bool delOpVrf(const string& vnet_name);


    VNetTable vnet_table_;
    VNetRequest request_;
    VNET_EXEC vnet_exec_;

    std::vector<VR_TYPE> vr_cntxt;
};

#endif // __VNETORCH_H
