"""
Cisco DHCP Snooping Configuration Script

This script automates the configuration of DHCP Snooping on multiple Cisco devices.
It connects to each device via SSH, identifies trunk/access ports, and applies 
appropriate DHCP snooping settings.

Dependencies:
- netmiko: pip install netmiko
- Custom modules: data.py, list_cisco.py
"""

from netmiko import ConnectHandler
from list_cisco import *     # python list of cisco device for configuration

# Global configuration commands for DHCP Snooping
GLOBAL_CONFIG_COMMANDS = [
    'ip dhcp snooping vlan 10,26-47,51,61,67',
    'ip dhcp snooping information option allow-untrusted',
    'no ip dhcp snooping information option',  # Disable option 82 by default
    'ip dhcp snooping'
]

def log_result(message):
    """Helper function to write results to log file"""
    with open('dhcp_snooping.log', 'a') as log_file:
        log_file.write(message + '\n')

def configure_dhcp_snooping():
    """Main function to configure DHCP snooping on all Cisco devices"""
    for cisco_device in list_cisco:
        # Establish SSH connection
        ssh_connection = ConnectHandler(
            device_type='cisco_ios',
            host=cisco_device,
            port=22,
            username=****,
            password=****
        )
        ssh_connection.enable()

        # Get device hostname for logging
        hostname = ssh_connection.find_prompt().strip('#')
        log_header = f"\n\n{'='*40}\nConfiguring {hostname}\n{'='*40}\n"
        
        # Get interface status information
        interfaces_output = ssh_connection.send_command("show interface status")
        interfaces_list = interfaces_output.split('\n')[2:]  # Remove header

        # Separate trunk and access ports
        trunk_ports = []
        access_ports = []
        
        for interface in interfaces_list:
            interface_info = interface.split()
            port_name = interface_info[0]
            
            # Check if interface is GigabitEthernet or FastEthernet and not trunk
            if ('Gi' in port_name or 'Fa' in port_name) and 'trunk' not in interface:
                access_ports.append(port_name)
            elif 'trunk' in interface:
                trunk_ports.append(port_name)

        # Write initial information to log file
        with open('dhcp_snooping.log', 'a') as log_file:
            log_file.write(log_header)
            log_file.write(f"Trunk Ports Detected:\n{trunk_ports}\n\n")
            log_file.write(f"Access Ports Detected:\n{access_ports}\n\n")
            log_file.write("Starting configuration...\n")

        # Configure trunk ports
        for trunk_port in trunk_ports:
            trunk_config = [
                f'interface {trunk_port}',
                'ip dhcp snooping trust',
                'exit'
            ]
            result = ssh_connection.send_config_set(trunk_config)
            log_result(f"Trunk Port {trunk_port} Config:\n{result}\n")

        # Configure access ports
        for access_port in access_ports:
            access_config = [
                f'interface {access_port}',
                'ip dhcp snooping limit rate 64',
                'exit'
            ]
            result = ssh_connection.send_config_set(access_config)
            log_result(f"Access Port {access_port} Config:\n{result}\n")

        # Apply global configuration
        global_config_result = ssh_connection.send_config_set(GLOBAL_CONFIG_COMMANDS)
        log_result(f"Global Configuration Result:\n{global_config_result}\n")

        # Save configuration
        save_result = ssh_connection.send_command("write memory")
        log_result(f"Configuration Saved:\n{save_result}\n")


if __name__ == "__main__":
    configure_dhcp_snooping()