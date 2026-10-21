import serial
import time
import getpass


class CiscoDevice:

    # Oppsett av variablar og tilkoplingsstandard
    def __init__(self, port, hostname, username, password, domain):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.domain = domain

        self.device = serial.Serial(
            port=port,
            baudrate=9600,
            timeout=1
        )

        time.sleep(2)

    def command(self, command, wait=1):
        """Send a command and return the device output."""

        self.device.write((command + "\r").encode())
        time.sleep(wait)

        return self.device.read_all().decode(errors="ignore")

    def connect(self):
        """Handle the Cisco initial configuration dialog."""

        self.device.write(b"\r")
        time.sleep(2)

        output = self.device.read_all().decode(errors="ignore")

        # Viser ein del av startup output for visualisering
        if output:
            print(output[-500:])

        # Sjekkar om initial configuration dialog dukkar opp og hopper over 
        if "initial configuration dialog" in output.lower():
            print("Initial configuration dialog detected.")

            self.device.write(b"no\r")
            time.sleep(2)

            self.device.write(b"\r")
            time.sleep(2)

            output = self.device.read_all().decode(errors="ignore")
            print(output[-300:])

    # Oppsett av standard variablar per eining
    def basic_config(self):
        print("\nConfiguring SSH...")

        self.command("")
        self.command("enable")
        self.command("configure terminal")

        self.command(f"hostname {self.hostname}")
        self.command(f"ip domain-name {self.domain}")

        self.command(
            f"username {self.username} "
            f"privilege 15 secret {self.password}"
        )

        output = self.command(
            "crypto key generate rsa modulus 2048",
            wait=5
        )

        # Ny nøkkel dersom allereie til stades
        if "yes/no" in output.lower():
            output = self.command("yes", wait=10)

        # Vis minimert og relevant output
        if output:
            print(output[-300:])

        self.command("ip ssh version 2")

        self.command("line vty 0 15")
        self.command("login local")
        self.command("transport input ssh")
        self.command("exit")

    # Set config på ruter frå input
    def configure_router(self, interface, ip, subnet, gateway):
        print("Configuring router network...")

        self.command(f"interface {interface}")
        self.command(f"ip address {ip} {subnet}")
        self.command("no shutdown")
        self.command("exit")

        self.command(
            f"ip route 0.0.0.0 0.0.0.0 {gateway}"
        )

    # Set config på L2 switch
    def configure_l2(self, vlan, ip, subnet, gateway, uplinks):
        print("Configuring Layer 2 switch...")

        self.command(f"vlan {vlan}")
        self.command("exit")

        for port in uplinks:
            self.command(f"interface {port}")
            self.command("switchport mode trunk")
            self.command(f"switchport trunk allowed vlan {vlan}")
            self.command("no shutdown")
            self.command("exit")

        self.command(f"interface vlan {vlan}")
        self.command(f"ip address {ip} {subnet}")
        self.command("no shutdown")
        self.command("exit")

        self.command(f"ip default-gateway {gateway}")

    # Set config på L3 switch
    def configure_l3(self, vlan, ip, subnet, gateway, access_ports):
        print("Configuring Layer 3 switch...")

        self.command("ip routing")

        self.command(f"vlan {vlan}")
        self.command("exit")

        for port in access_ports:
            self.command(f"interface {port}")
            self.command("switchport mode access")
            self.command(f"switchport access vlan {vlan}")
            self.command("no shutdown")
            self.command("exit")

        self.command(f"interface vlan {vlan}")
        self.command(f"ip address {ip} {subnet}")
        self.command("no shutdown")
        self.command("exit")

        if gateway:
            self.command(
                f"ip route 0.0.0.0 0.0.0.0 {gateway}"
            )

    def save(self):
        print("Saving configuration...")

        self.command("end")
        output = self.command("write memory", wait=2)

        if "error" in output.lower():
            print("Warning: Cisco reported an error while saving.")

    def close(self):
        if self.device and self.device.is_open:
            self.device.close()


# Sikring for feil/uregelmessig input
def parse_ports(text):
    """Split comma-separated port list, e.g. 'Fa0/2, Fa0/3'."""

    return [p.strip() for p in text.split(",") if p.strip()]


def main():

    print("================================")
    print(" Cisco Initial Configuration")
    print("================================")

    # Vel eining

    print("\nSelect device:")
    print("1. Router")
    print("2. Switch")

    device_choice = input("Choice: ").strip()

    if device_choice == "1":
        device_type = "router"

    elif device_choice == "2":

        print("\nSelect switch type:")
        print("1. Layer 2")
        print("2. Layer 3")

        switch_choice = input("Choice: ").strip()

        if switch_choice == "1":
            device_type = "l2"

        elif switch_choice == "2":
            device_type = "l3"

        else:
            print("Invalid switch choice.")
            return

    else:
        print("Invalid device choice.")
        return

    # Grunninnstillingar per eining, eksempel for port på Linux og Windows

    print("\n--- Device settings ---")

    port = input("Console port (e.g. COM3 or /dev/ttyUSB0): ")
    hostname = input("Hostname: ")
    username = input("SSH username: ")
    password = getpass.getpass("SSH password: ")
    domain = input("Domain name: ")

    device = None

    # Try for å sjekke om port er godkjent/eksisterar
    try:

        device = CiscoDevice(
            port,
            hostname,
            username,
            password,
            domain
        )

        device.connect()
        device.basic_config()

        # Input variablar for ruter

        if device_type == "router":

            print("\n--- Router network settings ---")

            interface = input("Interface: ")
            ip = input("IP address: ")
            subnet = input("Subnet mask: ")
            gateway = input("Default gateway: ")

            device.configure_router(
                interface,
                ip,
                subnet,
                gateway
            )

        # Val for L2 / L3 switch

        else:

            print("\n--- Switch network settings ---")

            vlan = input("Management VLAN: ")
            ip = input("Management IP: ")
            subnet = input("Subnet mask: ")

            if device_type == "l2":
                gateway = input("Default gateway: ")
                uplinks = parse_ports(
                    input("Uplink trunk ports (comma-separated): ")
                )

                device.configure_l2(
                    vlan,
                    ip,
                    subnet,
                    gateway,
                    uplinks
                )

            elif device_type == "l3":
                gateway = input("Default gateway (blank = none): ").strip()
                access_ports = parse_ports(
                    input("Ports in mgmt VLAN (comma-separated): ")
                )

                device.configure_l3(
                    vlan,
                    ip,
                    subnet,
                    gateway,
                    access_ports
                )

        device.save()

        print("\nConfiguration complete.")

    except serial.SerialException as error:
        print(f"\nSerial error: {error}")

    finally:
        if device:
            device.close()


if __name__ == "__main__":
    main()
