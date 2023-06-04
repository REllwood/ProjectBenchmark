import subprocess
import time


"""
Measures the wattage of the system using the `powermetrics` command-line tool.
This is currently not working as expected, and is returning null for all measurements, so it is not being used in the benchmarks.

Returns:
    float: The measured wattage of the system.
"""
def measure_wattage():
    subprocess.run(["powermetrics", "--samplers", "power", "--show-process-energy", "--show-global-wds"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # This is used to stablize the power measurement
    time.sleep(1)

    process = subprocess.run(["powermetrics", "--stop"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = process.stdout.decode()


    # Parse the power measurement data
    wattage = None
    for line in output.splitlines():
        if "Average Power" in line:
            wattage = float(line.split(":")[1].strip().split()[0])

    print("Measured Wattage:", wattage) 

    if wattage is None:
        wattage = 0  # Default to 0 so as not to cause issues with the benchmarks

    return wattage
