import socket
import subprocess
from ipaddress import ip_network, IPv4Interface


# ------------------- Utility Functions -------------------

def get_ip_and_subnet():
    """
    Retrieve the local IP address and subnet mask using ipconfig.
    """
    try:
        result = subprocess.run(['ipconfig'], stdout=subprocess.PIPE, text=True)
        output = result.stdout

        ip_address = None
        subnet_mask = None
        for line in output.splitlines():
            if "IPv4 Address" in line or "IPv4" in line:
                ip_address = line.split(":")[-1].strip()
            elif "Subnet Mask" in line:
                subnet_mask = line.split(":")[-1].strip()
            if ip_address and subnet_mask:
                break
        
        return ip_address, subnet_mask
    except Exception as e:
        print(f"Error retrieving IP and subnet mask: {e}")
        return None, None


def calculate_network_range(ip_address, subnet_mask):
    """
    Calculate the network range based on the IP address and subnet mask.
    """
    try:
        interface = IPv4Interface(f"{ip_address}/{subnet_mask}")
        network = interface.network
        return str(network)
    except Exception as e:
        print(f"Error calculating network range: {e}")
        return None


def ping_host(ip, timeout=1):
    """
    Ping a host to check if it is alive.
    """
    try:
        result = subprocess.run(
            ['ping', '-n', '1', '-w', str(timeout * 1000), str(ip)],
            stdout=subprocess.DEVNULL,
            timeout=timeout
        )
        return result.returncode == 0  # Return True if ping is successful
    except subprocess.TimeoutExpired:
        return False
    except Exception as e:
        print(f"Error pinging {ip}: {e}")
        return False


def get_hostname(ip):
    """
    Resolve the hostname of a given IP address.
    """
    try:
        return socket.gethostbyaddr(str(ip))[0]
    except socket.herror:
        try:
            # Fallback: Try resolving with .local for mDNS
            return socket.gethostbyaddr(f"{str(ip)}.local")[0]
        except (socket.herror, socket.gaierror):
            return "Unknown"
    except Exception as e:
        print(f"Error resolving hostname for {ip}: {e}")
        return "Unknown"


def get_mac_address(ip):
    """
    Retrieve the MAC address of a device using its IP address from the ARP table.
    """
    try:
        result = subprocess.run(['arp', '-a'], stdout=subprocess.PIPE, text=True)
        output = result.stdout
        for line in output.splitlines():
            if ip in line:
                return line.split()[1]  # Return MAC address from ARP table
    except Exception as e:
        print(f"Error retrieving MAC address for {ip}: {e}")
    return "Unknown"


# ------------------- Network Scanning -------------------

def scan_network(network_range):
    """
    Scan the network for active devices and retrieve their hostnames and MAC addresses.
    """
    print(f"Scanning network: {network_range}")
    
    devices = []
    
    for ip in ip_network(network_range, strict=False).hosts():
        print(f"Scanning IP: {ip}", end="")
        
        if ping_host(ip):
            hostname = get_hostname(ip)
            mac_address = get_mac_address(str(ip))
            devices.append((str(ip), hostname, mac_address))
            print(f" - Active (Hostname: {hostname}, MAC: {mac_address})")
        else:
            print(" - Inactive")
    
    return devices


# ------------------- Main Function -------------------

def main():
    """
    Main function to orchestrate the network scanning process.
    """
    # Step 1: Get local IP address and subnet mask
    ip_address, subnet_mask = get_ip_and_subnet()
    
    if not ip_address or not subnet_mask:
        print("Could not retrieve IP address or subnet mask.")
        return
    
    print(f"Local IP Address: {ip_address}")
    print(f"Subnet Mask: {subnet_mask}")
    
    # Step 2: Calculate network range
    network_range = calculate_network_range(ip_address, subnet_mask)
    
    if not network_range:
        print("Could not calculate network range.")
        return
    
    print(f"Network Range: {network_range}")
    
    # Step 3: Scan the network
    active_devices = scan_network(network_range)
    
    # Step 4: Display results
    if active_devices:
        print("\nIP Address\t\tHostname\t\tMAC Address")
        print("-------------------------------------------------------------")
        
        for ip, hostname, mac in active_devices:
            print(f"{ip}\t\t{hostname}\t\t{mac}")
    
    else:
        print("No active devices found.")


# ------------------- Entry Point -------------------

if __name__ == "__main__":
    main()
