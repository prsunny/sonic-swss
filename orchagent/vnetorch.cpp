#include <cassert>
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <exception>

#include "sai.h"
#include "macaddress.h"
#include "orch.h"
#include "request_parser.h"
#include "vnetorch.h"

extern sai_virtual_router_api_t* sai_virtual_router_api;
extern sai_object_id_t gSwitchId;


bool VNetOrch::addOperation(const Request& request)
{
    SWSS_LOG_ENTER();

    sai_attribute_t attr;
    vector<sai_attribute_t> attrs;
    set<string> peer_list = {};

    for (const auto& name: request.getAttrFieldNames())
    {
        if (name == "src_mac")
        {
            const auto& mac = request.getAttrMacAddress("src_mac");
            attr.id = SAI_VIRTUAL_ROUTER_ATTR_SRC_MAC_ADDRESS;
            memcpy(attr.value.mac, mac.getMac(), sizeof(sai_mac_t));
        }
        else if (name == "peer_list")
        {
            peer_list  = request.getAttrSet("peer_list");
        }
        else
        {
            SWSS_LOG_ERROR("Logic error: Unknown attribute: %s", name.c_str());
            continue;
        }
        attrs.push_back(attr);
    }

    const std::string& vnet_name = request.getKeyString(0);
    auto it = vnet_table_.find(vnet_name);
    if (it == std::end(vnet_table_))
    {
        auto l_fn = [&] (sai_object_id_t& router_id) {

            sai_status_t status = sai_virtual_router_api->create_virtual_router(&router_id,
                                                                                gSwitchId,
                                                                                static_cast<uint32_t>(attrs.size()),
                                                                                attrs.data());
            if (status != SAI_STATUS_SUCCESS)
            {
                SWSS_LOG_ERROR("Failed to create virtual router name: %s, rv: %d",
                               vnet_name.c_str(), status);
                return false;
            }
            return true;
        };

        /*
         * Create ingress and egress VRF if required
         */
        set<sai_object_id_t> vr_ent;

        for (auto vr_type : vr_cntxt)
        {
            sai_object_id_t router_id;
            if (vr_type != VR_TYPE::VR_INVALID && l_fn(router_id))
            {
                vr_ent.insert(router_id);
            }
        }

        VNetObject_T vnet_obj(new VNetObject(vnet_name, vr_ent, peer_list));
        vnet_table_[vnet_name] = std::move(vnet_obj);

        SWSS_LOG_NOTICE("VNET '%s' was added ", vnet_name.c_str());

    }
    else
    {
        // Update an existing vrfs

        set<sai_object_id_t> vr_ent = getVRids(vnet_name);

        for (const auto& attr: attrs)
        {
            for (auto it : vr_ent)
            {
                sai_status_t status = sai_virtual_router_api->set_virtual_router_attribute(it, &attr);
                if (status != SAI_STATUS_SUCCESS)
                {
                    SWSS_LOG_ERROR("Failed to update virtual router attribute. VNET name: %s, rv: %d",
                                    vnet_name.c_str(), status);
                    return false;
                }
            }
        }

        SWSS_LOG_NOTICE("VNET '%s' was updated", vnet_name.c_str());
    }

    return true;
}

bool VNetOrch::delOperation(const Request& request)
{
    SWSS_LOG_ENTER();

    const std::string& vnet_name = request.getKeyString(0);
    if (vnet_table_.find(vnet_name) == std::end(vnet_table_))
    {
        SWSS_LOG_ERROR("VNET '%s' doesn't exist", vnet_name.c_str());
        return true;
    }

    set<sai_object_id_t> vr_ent = getVRids(vnet_name);
    for (auto it : vr_ent)
    {
        sai_status_t status = sai_virtual_router_api->remove_virtual_router(it);
        if (status != SAI_STATUS_SUCCESS)
        {
            SWSS_LOG_ERROR("Failed to remove virtual router name: %s, rv:%d", vnet_name.c_str(), status);
            return false;
        }

    }

    SWSS_LOG_NOTICE("VNET '%s' was removed", vnet_name.c_str());

    return true;
}
