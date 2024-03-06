import allure
import pytest
import json
import os
import time
from tests.common.utilities import (wait, wait_until)
from tests.common.helpers.assertions import pytest_assert

TIMEOUT = 120

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.device_type('vs')
]

def load_new_config(duthost, path):
    cfggen_cmd = "sudo sonic-cfggen -j {} --write-to-db".format(path)
    reload_cmd = "sudo config reload {} -y".format(path)
    duthost.shell(cfggen_cmd)
    time.sleep(10)
    duthost.shell(reload_cmd)
    wait(TIMEOUT, "For config to reload \n")

def test_snmp_pg_counters(duthosts, enum_rand_one_per_hwsku_frontend_hostname, localhost, creds_all_duts):
    """
    Test SNMP PG counters
      - Set "create_only_config_db_buffers" to true in config db, to create only relevant pg counters
      - Remove one of the buffer queues, Ethernet0|3-4 is chosen arbitrary
      - Using snmpwalk compare number of PG counters on Ethernet0, assuming there will be 8 less after
        removing the buffer. (Assuming unicast only, 4 pg counters for each lane in this case)
    """

    duthost = duthosts[enum_rand_one_per_hwsku_frontend_hostname]
    hostip = duthost.host.options['inventory_manager'].get_host(
        duthost.hostname).vars['ansible_host']
    oid = '1.3.6.1.4.1.9.9.580.1.5.5.1.4.1'
    dut_command = "docker exec snmp snmpwalk -v2c -c {} {} {}".format(
        creds_all_duts[duthost.hostname]['snmp_rocommunity'], hostip, oid
    )
    
    # Add create_only_config_db_buffers entry to device metadata to enable pg counters optimization
    duthost.shell("sonic-cfggen -d --print-data > /etc/sonic/orig_config_db.json")
    data = json.loads(duthost.shell("cat /etc/sonic/orig_config_db.json", verbose=False)['stdout'])
    data['DEVICE_METADATA']["localhost"]["create_only_config_db_buffers"] = "true"
    
    path = "/tmp/modified_config_db.json"
    duthost.copy(content=json.dumps(data, indent=4), dest=path)
    load_new_config(duthost, path)

    # Get number of pg counters of Ethernet0 prior to removing buffer queue
    output_pre = duthost.shell(dut_command)
    pg_counters_cnt_pre = len(output_pre["stdout_lines"])

    # Remove buffer queue and reload
    del data['BUFFER_QUEUE']["Ethernet0|3-4"]
    duthost.copy(content=json.dumps(data, indent=4), dest=path)
    load_new_config(duthost, path)

    # Get number of pg counters of Ethernet0 after to removing buffer queue
    output_post = duthost.shell(dut_command)
    pg_counters_cnt_post = len(output_post["stdout_lines"])
    
    # Cleanup
    load_new_config(duthost, "/etc/sonic/orig_config_db.json")

    pytest_assert((pg_counters_cnt_pre - pg_counters_cnt_post) == 8, "Expected {} PG counters after modification, got {} instead".format((pg_counters_cnt_pre-8), pg_counters_cnt_post))
