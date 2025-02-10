import socket
import subprocess
from ipaddress import ip_network
from concurrent.futures import ThreadPoolExecutor


def get_local_ip():
    """
    Retrieve the local IP address of the machine.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Connect to Google's DNS server
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception as e:
        print(f"Error retrieving local IP: {e}")
        return None


def calculate_network_range(ip_address, subnet_mask="255.255.255.0"):
    """
    Calculate the network range based on the IP address and subnet mask.
    """
    try:
        network = ip_network(f"{ip_address}/{subnet_mask}", strict=False)
        return network
    except Exception as e:
        print(f"Error calculating network range: {e}")
        return None


def ping_host(ip):
    """
    Ping a host to check if it is alive.
    """
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-w', '1', str(ip)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0  # Return True if ping is successful
    except Exception as e:
        print(f"Error pinging {ip}: {e}")
        return False


def get_mac_address(ip):
    """
    Retrieve the MAC address of a device using its IP address from the ARP table.
    """
    try:
        result = subprocess.run(['arp', '-n'], stdout=subprocess.PIPE, text=True)
        output = result.stdout
        for line in output.splitlines():
            if ip in line:
                parts = line.split()
                if len(parts) >= 3:
                    return parts[2]  # Return MAC address
    except Exception as e:
        print(f"Error retrieving MAC address for {ip}: {e}")
    return None


def scan_ip(ip, target_mac):
    """
    Scan a single IP to check if its MAC matches the target MAC.
    """
    if ping_host(ip):
        mac_address = get_mac_address(str(ip))
        if mac_address and mac_address.lower() == target_mac.lower():
            return str(ip)
    return None


def scan_network_concurrently(network, target_mac, num_threads=10):
    """
    Scan the network concurrently using multiple threads to find the target MAC's IP.
    """
    print(f"Scanning network: {network} for MAC: {target_mac}")
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(scan_ip, ip, target_mac) for ip in network.hosts()]
        
        for future in futures:
            result = future.result()
            if result:  # If a matching IP is found
                return result
    
    return None


def main():
    # Step 1: Get local IP address
    local_ip = get_local_ip()
    
    if not local_ip:
        print("Could not determine local IP address.")
        return
    
    print(f"Local IP Address: {local_ip}")
    
    # Step 2: Calculate network range
    subnet_mask = "255.255.255.0"  # Default subnet mask (adjust if necessary)
    network_range = calculate_network_range(local_ip, subnet_mask)
    
    if not network_range:
        print("Could not calculate network range.")
        return
    
    print(f"Network Range: {network_range}")
    
    # Step 3: Input target MAC address
    target_mac = input("Enter the MAC address to search for (e.g., AA:BB:CC:DD:EE:FF): ").strip()
    
    # Step 4: Scan the network concurrently
    ip_address = scan_network_concurrently(network_range, target_mac)
    
    # Step 5: Display results
    if ip_address:
        print(f"The IP address for MAC {target_mac} is: {ip_address}")
    else:
        print(f"No device found with MAC address {target_mac} on the network.")


if __name__ == "__main__":
    main()
