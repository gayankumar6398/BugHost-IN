import subprocess
import ipaddress
import requests
import shutil
import socket
import ssl
import os
import asyncio
from rich.console import Console
from rich import print
from concurrent.futures import ThreadPoolExecutor
import re
import sys
import aiohttp
import cfscrape
import time
import colorama
from colorama import Fore, Style

colorama.init()

loop = asyncio.get_event_loop()

console = Console()

def subdomain_finder():
    hostname = input("Enter a hostname to find subdomains: ")

    url = f"https://crt.sh/?q=%.{hostname}&output=json"
    response = requests.get(url)

    subdomains = set()

    if response.status_code == 200:
        data = response.json()

        for entry in data:
            name_value = entry["name_value"]
            if name_value != hostname and not name_value.startswith("*."):
                subdomains.add(name_value.replace("www.", ""))  # Add the subdomain to the set, removing 'www.' prefix

    if subdomains:
        print(f"Subdomains for {hostname}:")
        print(hostname)  # Display the root domain

        # Write subdomains to a file
        with open("subdomains.txt", "w") as file:
            for subdomain in subdomains:
                print(subdomain)
                file.write(subdomain + "\n")

        # Filter out duplicate subdomains and write to hosts.txt
        unique_lines = set()
        with open("subdomains.txt", 'r') as f:
            for line in f:
                unique_lines.add(line.strip())

        with open("hosts.txt", 'w') as f:
            for line in unique_lines:
                f.write(line + '\n')

        print('Filtered subdomains saved to hosts.txt')

        # Delete subdomains.txt
        import os
        os.remove("subdomains.txt")

    else:
        print(f"No subdomains found for {hostname}")

    if response.status_code != 200:
        print("Unable to retrieve subdomains. Please try again later.")

def get_ip_address(hostname):
    try:
        ip_address = socket.gethostbyname(hostname)
        return ip_address
    except socket.gaierror:
        return None

def get_server_type(hostname, timeout=3):
    try:
        response = requests.get(f"http://{hostname}", timeout=timeout)
        server_type = response.headers.get("Server")
        if server_type:
            return server_type
        else:
            return "Unknown"
    except requests.RequestException:
        return "Unknown"  # Return "Unknown" if server type cannot be determined

def get_http_status_code(hostname, timeout):
    try:
        response = requests.head(f"http://{hostname}", timeout=timeout)
        return response.status_code
    except requests.RequestException:
        return -1  # Return -1 if status code cannot be determined

def host_scanner():
    try:
        with open("hosts.txt", "r") as file:
            hosts = file.read().splitlines()
            timeout = min(3, max(1, len(hosts) // 100))  # Adjust timeout based on number of hostnames
            for host in hosts:
                ip_address = get_ip_address(host)
                if ip_address:
                    server_type = get_server_type(host, timeout)
                    status_code = get_http_status_code(host, timeout)
                    if status_code == 200 and "cloudflare" in server_type.lower():
                        print(f"\033Hostname: {host} - IP Address: {ip_address} - Server Type: {server_type} - HTTP Status Code: {status_code}\033")  # Green color
                    else:
                        print(f"Hostname: {host} - IP Address: {ip_address} - Server Type: {server_type} - HTTP Status Code: {status_code}")
                else:
                    print(f"Hostname: {host} - IP Address: Not found - Server Type: Not checked - HTTP Status Code: Not checked")
    except FileNotFoundError:
        print("hosts.txt file not found. Run the Subdomain Finder tool first.")

def check_ip(ip, port, timeout):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    result = sock.connect_ex((ip, port))
    sock.close()
    return result == 0

def print_color(text, color):
    colors = {
        "red": Fore.RED,
        "green": Fore.GREEN,
        "reset": Style.RESET_ALL
    }
    print(f"{colors[color]}{text}{colors['reset']}")

def get_cloudflare_ranges():
    url = "https://www.cloudflare.com/ips-v4"
    response = requests.get(url)
    if response.status_code == 200:
        return response.text.splitlines()
    else:
        return []

# Get Cloudflare IP ranges
cloudflare_ranges = get_cloudflare_ranges()

def ip_scanner():
    ip_range_cidr = input("Enter IP range in CIDR notation (e.g., 192.168.1.0/24): ")
    timeout = float(input("Enter connection timeout (in seconds): "))

    # Get IP addresses from CIDR range
    ip_list = [str(ip) for ip in ipaddress.IPv4Network(ip_range_cidr, strict=False)]

    for ip in ip_list:
        connected = check_ip(ip, 80, timeout)
        is_cloudflare_ip = any(ipaddress.ip_address(ip) in ipaddress.ip_network(cloudflare_range) for cloudflare_range in cloudflare_ranges)

        if connected and is_cloudflare_ip:
            print_color(f"IP: {ip} - Connected (Cloudflare)", "green")
        elif not connected and is_cloudflare_ip:
            print_color(f"IP: {ip} - Not connected (Cloudflare)", "red")
        else:
            print_color(f"IP: {ip} - Not connected (Other server)", "red")

def check_port(ip, port, timeout):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    result = sock.connect_ex((ip, port))
    sock.close()
    return result == 0

def port_scanner():
    ip_or_cidr = input("Enter an IP address or CIDR to scan for open ports: ")
    try:
        network = ipaddress.ip_network(ip_or_cidr)
        if network.num_addresses > 1:  # CIDR range
            for ip in network.hosts():
                print(f"\nScanning ports for IP: {ip}")
                for port in [53, 80, 443]:  # Ports to check: DNS-53, HTTP-80, HTTPS-443
                    connected = check_port(str(ip), port, 0.5)
                    if connected:
                        print(f"IP: {ip} - Port: {port} - Open")
                    else:
                        print(f"IP: {ip} - Port: {port} - Closed")
        else:  # Single IP
            ip = str(network.network_address)
            print(f"\nScanning ports for IP: {ip}")
            for port in [53, 80, 443]:  # Ports to check: DNS-53, HTTP-80, HTTPS-443
                connected = check_port(ip, port, 0.5)
                if connected:
                    print(f"IP: {ip} - Port: {port} - Open")
                else:
                    print(f"IP: {ip} - Port: {port} - Closed")
    except ValueError:
        print("Invalid input. Please enter a valid IP address or CIDR.")

def reverse_ip_lookup():
    ip_to_lookup = input("Enter the IP to perform reverse lookup: ")
    try:
        response = requests.get(f"https://api.hackertarget.com/reverseiplookup/?q={ip_to_lookup}")
        if response.status_code == 200:
            hostnames = response.text.splitlines()
            if hostnames:
                print(f"Hostname(s) for {ip_to_lookup}:")
                for hostname in hostnames:
                    print(hostname)
            else:
                print("No hostnames found for the given IP.")
        else:
            print("Unable to perform the reverse IP lookup. Please try again.")
    except requests.RequestException as e:
        print(f"Error: {e}")

def bugscanner_subdomain_scan():
    target_file = 'hosts.txt'
    target_proxy = console.input("[yellow]Enter proxy IP[/yellow]: ")
    target_port = console.input("[yellow]Enter target port[/yellow] (default is 443): ") or '443'

    try:
        bugscanner_command = f"bugscanner --mode direct --proxy {target_proxy} --port {target_port} {target_file}"
        os.system(bugscanner_command)
        console.print("[red]Scan complete[/red].")
    except Exception as e:
        print(f"Error during scan: {e}")

    choice = console.input("[yellow]Do you want to go back to the main menu?[/yellow][red](y/n)[/red]: ")
    if choice.lower() == 'y':
        main_menu()
    elif choice.lower() == 'n':
        console.print("[bold cyan]Exiting script.[/bold cyan]")
        sys.exit()

def bugscanner_cdn_ssl_scan():
    target_file = 'hosts.txt'
    new_target = console.input("Enter a new target (leave blank to keep [blue]sa.zain.com[/blue]): ")
    target = new_target if new_target else "sa.zain.com"
    target_proxy = console.input("[yellow]Enter proxy IP[/yellow]: ")
    bugscanner_command = f"bugscanner-go scan cdn-ssl --proxy-filename {target_file} --target {target}"
    os.system(bugscanner_command)
    print("Scan complete..")
    
    choice = console.input("[yellow]Do you want to go back to the main menu?[/yellow][red](y/n)[/red]: ")
    if choice.lower() == 'y':
        main_menu()
    elif choice.lower() == 'n':
        console.print("[bold cyan]Exiting script.[/bold cyan]")
        sys.exit()

def bugscanner_sni_scan():
    target_file = 'hosts.txt'
    bugscanner_command = f"bugscanner-go scan sni -f {target_file}"
    os.system(bugscanner_command)

    print("Scan complete.")
    
    choice = console.input("[yellow]Do you want to go back to the main menu?[/yellow][red](y/n)[/red]: ")
    if choice.lower() == 'y':
        main_menu()
    elif choice.lower() == 'n':
        console.print("[bold cyan]Exiting script.[/bold cyan]")
        sys.exit()

# Rest of the code remains unchanged

def cloudip_scan():
    try:
        target_range = console.input("[yellow]Enter IP range [/yellow](e.g., 192.0.0.0/24): ")
        net4 = ipaddress.ip_network(target_range)
        addresses = [str(host) for host in net4.hosts()]
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.google.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'TE': 'Trailers',
        }

        with ThreadPoolExecutor(max_workers=20) as executor:
            https_futures = [executor.submit(check_address, re.sub(r'^(https?://)?', r'https://', address.strip()), headers=headers) for address in addresses]

            for future in https_futures:
                future.result()

        print("HTTPS Scan complete.")
        print("[bold cyan]Starting HTTP Scan...[/bold cyan]")
        time.sleep(2)
        headers = {}
        with ThreadPoolExecutor(max_workers=20) as executor:
            http_futures = [executor.submit(check_address, f'http://{address.strip()}', headers=headers) for address in addresses]
            for future in http_futures:
                future.result()

        print("Scan complete.")
    
        choice = console.input("[yellow]Do you want to go back to the main menu?[/yellow][red](y/n)[/red]: ")
        if choice.lower() == 'y':
            main_menu()
        elif choice.lower() == 'n':
            console.print("[bold cyan]Exiting script.[/bold cyan]")
            sys.exit()

    except ValueError as e:
        print(f'\nError: {str(e)}')
        print("Please enter a valid IP range.")
        cloudip_scan()

# Inside the check_address function
def check_address(address, headers=None):
    try:
        scraper = cfscrape.create_scraper()
        headers = headers or {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
        }
        
        # Update: Allow redirects
        response = scraper.get(address, headers=headers, timeout=60, allow_redirects=True, verify=False)
        
        # Check for a valid response
        if response.ok:
            status_code = response.status_code
            server = response.headers.get('Server')
            
            if status_code == 200:
                print_status(address, status_code, server)
            else:
                result = f"[-] {address} - {status_code} {response.reason}"
                console.print(f"[-] {address} - [red]{status_code} {response.reason}[/]")
        else:
            print_status(address, response.status_code, None)  # Treat non-OK responses as valid for simplicity

    except requests.exceptions.RequestException as e:
        if isinstance(e, requests.exceptions.SSLError):
            result = f"[-] {address} - SSL Error: {str(e)}"
            console.print(f"[-] {address} - [red]SSL Error: {str(e)}[/]")
        else:
            # Catch InvalidURL locally and print a custom message without traceback
            if isinstance(e, requests.exceptions.InvalidURL):
                console.print(f"[-] {address} - [red]Invalid URL: {address}[/]")
            else:
                result = f"[-] {address} - Connection Error: {str(e)}"
                console.print(f"[-] {address} - [red]Connection Error: {str(e)}[/]")
    except Exception as ex:
        result = f"[-] {address} - An unexpected error occurred: {str(ex)}"
        console.print(f"[-] {address} - [red]An unexpected error occurred: {str(ex)}[/]")

# Rest of the code remains unchanged


def print_status(address, status_code, server):
    if server:
        server = server.lower()
        if any(name in server for name in ['cloudflare', 'cloudfront', 'akamai', 'AkamaiGHost']):
            result = f"[+] {address} - [green]{status_code} OK ([green]{server}[/])"
        elif any(name in server for name in ['varnish', 'litespeed', 'fastly', 'nginx']):
            result = f"[+] {address} - [on_green]{status_code} OK ([on_green]{server}[/])"
        else:
            result = f"[+] {address} - [purple]{status_code} OK ([purple]{server}[/])"
    else:
        result = f"[+] {address} - [on_red]{status_code} OK (Server type unknown)"

    print(result)
    with open('hosts.txt', 'a') as file:
        file.write(address + '\n')

def main_menu():
    os.system('clear')
    fpi = f'''██████╗ ██╗   ██╗ ██████╗ ██╗  ██╗ ██████╗ ███████╗████████╗   ██╗███╗   ██╗
██╔══██╗██║   ██║██╔════╝ ██║  ██║██╔═══██╗██╔════╝╚══██╔══╝   ██║████╗  ██║
██████╔╝██║   ██║██║  ███╗███████║██║   ██║███████╗   ██║█████╗██║██╔██╗ ██║
██╔══██╗██║   ██║██║   ██║██╔══██║██║   ██║╚════██║   ██║╚════╝██║██║╚██╗██║
██████╔╝╚██████╔╝╚██████╔╝██║  ██║╚██████╔╝███████║   ██║      ██║██║ ╚████║
╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝      ╚═╝╚═╝  ╚═══╝
                                                                            
    '''
    
    B = "=========by: DragonSlayerX \n                         Telegram :@dragon_slayer10 \n\n"
    
    for char in B:
        if char.isalpha():
            console.print(char, end='', style="bold cyan")
        else:
            console.print(char, end='')
        time.sleep(0.1)

    for char in fpi:
        print(char, end='')
        time.sleep(0.001)

    while True:
        console.print("\n[bold cyan]Please select an option:[/bold cyan]")
        console.print("[bold blue][1] Subdomain Finder[/bold blue]")
        console.print("[bold green][2] Host Scanner[/bold green]")
        console.print("[bold yellow][3] IP Scanner[/bold yellow]")
        console.print("[bold red][4] Port Scanner[/bold red]")
        console.print("[bold magenta][5] Reverse IP Lookup[/bold magenta]")
        console.print("[bold blue][6] Bugscanner Subdomain Scan[/bold blue]")
        console.print("[bold green][7] Bugscanner CDN-SSL Scan[/bold green]")
        console.print("[bold yellow][8] Bugscanner SNI Scan[/bold yellow]")
        console.print("[bold red][9] CloudIP Scan[/bold red]")
        console.print("[bold cyan][0] Exit Script[/bold cyan]")

        choice = console.input("[magenta][-][/magenta] Enter your choice (0-9):> ")

        if choice == '1':
            subdomain_finder()
        elif choice == '2':
            host_scanner()
        elif choice == '3':
            ip_scanner()
        elif choice == '4':
            port_scanner()
        elif choice == '5':
            reverse_ip_lookup()
        elif choice == '6':
            bugscanner_subdomain_scan()
        elif choice == '7':
            bugscanner_cdn_ssl_scan()
        elif choice == '8':
            bugscanner_sni_scan()
        elif choice == '9':
            cloudip_scan()
        elif choice == '0':
            console.print("[bold cyan]Exiting script.[/bold cyan]")
            break
        else:
            console.print("[bold red]Invalid choice. Please select a valid option.[/bold red]")

if __name__ == "__main__":
    main_menu()
