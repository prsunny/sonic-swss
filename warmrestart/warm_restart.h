#ifndef SWSS_WARM_RESTART_H
#define SWSS_WARM_RESTART_H

#include <string>
#include "dbconnector.h"
#include "table.h"

#define MAXIMUM_WARMRESTART_TIMER_VALUE 9999

namespace swss {

class WarmStart
{
public:
	enum WarmStartState
	{
	    INITIALIZED,
	    RESTORED,
	    RECONCILED,
	};

    typedef std::map<WarmStartState, std::string>  WarmStartStateNameMap;
    static const WarmStartStateNameMap warmStartStateNameMap;

    static WarmStart &getInstance(void);

    static void initialize(const std::string &app_name,
                           const std::string &docker_name = "swss");

    static bool checkWarmStart(const std::string &app_name,
                               const std::string &docker_name = "swss");

    static bool isWarmStart(void);

    static void setWarmStartState(const std::string &app_name,
                                  WarmStartState     state);

    static uint32_t getWarmStartTimer(const std::string &app_name,
                                      const std::string &docker_name ="swss");

private:
    std::shared_ptr<swss::DBConnector>   m_stateDb;
    std::shared_ptr<swss::DBConnector>   m_cfgDb;
    std::unique_ptr<Table>               m_stateWarmRestartTable;
    std::unique_ptr<Table>               m_cfgWarmRestartTable;
    bool                                 m_initialized;
    bool                                 m_enabled;
};

}

#endif
