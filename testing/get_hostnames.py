import socket
import subprocess
from ipaddress import ip_network, IPv4Interface

def get_ip_and_subnet():
    """
    Retrieve the local IP address and subnet mask using ipconfig.
    """
    try:
        # Run ipconfig command and capture output
        result = subprocess.run(['ipconfig'], stdout=subprocess.PIPE, text=True)
        output = result.stdout

        # Parse the output to find IPv4 address and subnet mask
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
    Calculate the network range based on IP address and subnet mask.
    """
    try:
        interface = IPv4Interface(f"{ip_address}/{subnet_mask}")
        network = interface.network
        return str(network)
    except Exception as e:
        print(f"Error calculating network range: {e}")
        return None

def ping_host(ip):
    """
    Ping a host to check if it is alive.
    """
    try:
        result = subprocess.run(['ping', '-n', '1', '-w', '100', str(ip)], stdout=subprocess.DEVNULL)
        return result.returncode == 0  # Return True if ping is successful
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
        return "Unknown"

def scan_network(network_range):
    """
    Scan the network for active IPs and retrieve their hostnames.
    """
    print(f"Scanning network: {network_range}")
    devices = []
    
    for ip in ip_network(network_range, strict=False).hosts():
        print(f"Scanning IP: {ip}", end="")
        if ping_host(ip):
            hostname = get_hostname(ip)
            devices.append((str(ip), hostname))
            print(f" - Active (Hostname: {hostname})")
        else:
            print(" - Inactive")
    
    return devices

    

def main():
    # Get local IP address and subnet mask
    ip_address, subnet_mask = get_ip_and_subnet()
    
    if not ip_address or not subnet_mask:
        print("Could not retrieve IP address or subnet mask.")
        return
    
    print(f"Local IP Address: {ip_address}")
    print(f"Subnet Mask: {subnet_mask}")
    
    # Calculate network range
    network_range = calculate_network_range(ip_address, subnet_mask)
    
    if not network_range:
        print("Could not calculate network range.")
        return
    
    print(f"Network Range: {network_range}")
    
    # Scan the network
    active_devices = scan_network(network_range)
    
    # Display results
    if active_devices:
        print("\nIP Address\t\tHostname")
        print("---------------------------------------")
        for ip, hostname in active_devices:
            print(f"{ip}\t\t{hostname}")
    else:
        print("No active devices found.")

if __name__ == "__main__":
    main()
