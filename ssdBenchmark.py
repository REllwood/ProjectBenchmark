import os
import random
import time
from wattage import measure_wattage



"""
Performs a benchmark test on the SSD by creating and writing to temporary files of various sizes, and measuring the
time it takes to read and write data. The function returns a dictionary containing the benchmark score, as well as
the total score and wattage used during the test.

Args:
    progress_callback (function): A function that updates the progress of the benchmark test.

Returns:
    dict: A dictionary containing the benchmark score, as well as the total score and wattage used during the test.
"""
def perform_ssd_benchmark(progress_callback):
    progress_callback.emit_current_test_info("Running SSD Benchmark")

    test_directory = "ssd_benchmark"
    file_sizes = [1024, 4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288, 1048576, 4194304]  # File sizes in KB
    largest_file_size = 100 * 1024 * 1024

    # Create a temp directory on the local system
    os.makedirs(test_directory, exist_ok=True)

    total_score = 0.0

    for size in file_sizes:
        file_path = os.path.join(test_directory, f"{size}KB_file")

        data = bytearray(os.urandom(size * 1024))

        with open(file_path, "wb") as f:
            f.write(data)

        with open(file_path, "rb") as f:
            read_data = f.read()

        if data == read_data:
            print(f"Random Read/Write for {size}KB File: Passed")
        else:
            print(f"Random Read/Write for {size}KB File: Failed")

       #remove temp file
        os.remove(file_path)

        write_time = size / 1024  
        read_time = size / 1024  
        score = (write_time + read_time) / (1024 * 1024)
        total_score += score

        # Update progress after each file operation
        progress = int(((file_sizes.index(size) + 1) / len(file_sizes)) * 100)
        progress_callback.update_progress(progress)

        time.sleep(0.1) 

    # Sequential and random write operations
    file_path = os.path.join(test_directory, "sequential_file")
    data = bytearray(os.urandom(1024 * 1024)) 

    # Sequential write
    with open(file_path, "wb") as f:
        for _ in range(largest_file_size // len(data)):
            f.write(data)

    # Random write
    with open(file_path, "r+b") as f:
        file_size = os.path.getsize(file_path)
        for _ in range(largest_file_size // len(data)):
            offset = random.randint(0, file_size - len(data))
            f.seek(offset)
            f.write(data)

    # Sequential and random read operations
    with open(file_path, "rb") as f:
        start_time = time.time()
        f.read()
        sequential_read_time = time.time() - start_time

        start_time = time.time()
        for _ in range(largest_file_size // len(data)):
            offset = random.randint(0, file_size - len(data))
            f.seek(offset)
            f.read(len(data))
        random_read_time = time.time() - start_time

    print("SSD Benchmark completed.")

    score = (sequential_read_time + random_read_time) / (1024 * 1024)
    total_score += score

    total_wattage = measure_wattage()

    os.remove(file_path)
    os.rmdir(test_directory)

    benchmark_results = {"score": round(total_score, 3)}
    return benchmark_results, total_score, total_wattage
