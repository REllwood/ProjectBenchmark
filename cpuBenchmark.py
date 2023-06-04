import time
import multiprocessing

from wattage import measure_wattage


def fibonacci(n):
    if n <= 1:
        return n
    else:
        return fibonacci(n - 1) + fibonacci(n - 2)


def calculate_primes(n):
    primes = []
    for num in range(2, n + 1):
        is_prime = True
        for i in range(2, int(num ** 0.5) + 1):
            if num % i == 0:
                is_prime = False
                break
        if is_prime:
            primes.append(num)
    return primes



"""
Runs a single-core test by performing intensive calculations on the Fibonacci sequence.

Args:
    progress_callback (ProgressCallback): An object that allows the function to update the progress of the test.

Returns:
    float: The score of the test, which is the average time taken to calculate the Fibonacci sequence.
"""
def perform_single_core_test(progress_callback):
    progress_callback.emit_current_test_info("Running Single-Core Test")

    num_calculations = 10
    calculation_results = []

    for i in range(num_calculations):
        start_time = time.time()
        fibonacci_result = fibonacci(35)
        elapsed_time = time.time() - start_time
        calculation_results.append(elapsed_time)

        progress = int(((i + 1) / num_calculations) * 100)
        progress_callback.update_progress(progress)

    total_time = sum(calculation_results)
    score = total_time / len(calculation_results)

    return score


def worker(start, end):
    result = 0
    for i in range(start, end):
        result += fibonacci(35)
    return result


"""
Runs a multi-core test by performing intensive calculations on the Fibonacci sequence using multiple processes.

Args:
    progress_callback (ProgressCallback): An object that allows the function to update the progress of the test.

Returns:
    float: The score of the test, which is the average time taken to calculate the Fibonacci sequence using multiple processes.
"""
def perform_multi_core_test(progress_callback):
    progress_callback.emit_current_test_info("Running Multi-Core Test")

    num_processes = multiprocessing.cpu_count()
    num_calculations = 10
    chunk_size = num_calculations // num_processes

    pool = multiprocessing.Pool(processes=num_processes)
    results = []

    for i in range(num_processes):
        start = i * chunk_size
        end = (i + 1) * chunk_size
        result = pool.apply_async(worker, (start, end))
        results.append(result)

    pool.close()

    completed_results = 0
    while completed_results < num_calculations:
        completed_results = sum(result.ready() for result in results)
        progress = int((completed_results / num_calculations) * 100)
        progress_callback.update_progress(progress)
        time.sleep(0.01)

    pool.join()

    calculation_results = [result.get() for result in results]
    total_time = sum(calculation_results)
    score = total_time / num_calculations

    print("Multi-Core Test completed.")
    print("Score:", format_score(score))

    return score

"""
Runs a CPU benchmark by performing intensive calculations on the Fibonacci sequence using both single-core and multi-core tests.

Args:
    progress_callback (ProgressCallback): An object that allows the function to update the progress of the test.

Returns:
    tuple: A tuple containing the benchmark results, total score, and total wattage measurement.
"""
def perform_cpu_benchmark(progress_callback):
    benchmark_results = {}

    # Single-Core Test
    single_core_score = perform_single_core_test(progress_callback)
    benchmark_results["Single-Core Test"] = single_core_score

    # Reset progress bar to 0% before the multi-core test
    progress_callback.update_progress(0)

    # Multi-Core Test
    multi_core_score = perform_multi_core_test(progress_callback)
    benchmark_results["Multi-Core Test"] = multi_core_score

    # Calculate the total score based on individual test scores
    total_score = sum(benchmark_results.values())
    total_wattage = measure_wattage()
    return benchmark_results, total_score, total_wattage


def format_score(score):
    return round(abs(score), 3)
