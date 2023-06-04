import time
import psutil
from wattage import measure_wattage


"""
Runs a RAM benchmark by generating a large list to consume memory and measuring the total memory used.

Args:
    progress_callback: A callback function to report progress updates.

Returns:
    A score representing the total memory used as a fraction of the specified memory size.

"""
def perform_ram_benchmark(progress_callback):
    progress_callback.emit_current_test_info("Running RAM Benchmark")

    # Generate a large list to consume memory
    memory_list = []
    memory_size = 2048  # Size in MB

    num_iterations = 20
    iteration_size = memory_size // num_iterations

    for i in range(num_iterations):
        memory_list.extend([0] * (iteration_size * 1024 * 1024))  # Allocate memory in MB, adjust this based on your system, will update this to autogenerate based on systems memory

        progress = int(((i + 1) / num_iterations) * 100)
        progress_callback.update_progress(progress)

        time.sleep(0.05) 

        for j in range(len(memory_list)):
            memory_list[j] += 1

    total_memory_used = len(memory_list)
    score = total_memory_used / (memory_size * 1024) #Need to look into how to improve this as at the moment it is not a good way to generate scores


    return score
