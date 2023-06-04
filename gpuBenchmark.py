import numpy as np
import tensorflow as tf
from PyQt6.QtCore import QThread, pyqtSignal
import concurrent.futures
from wattage import measure_wattage


class BenchmarkWorker(QThread):
    progress_updated = pyqtSignal(int)
    current_test_info = pyqtSignal(str)

    def run(self):
        benchmark_results, total_score, total_wattage = perform_gpu_benchmark(self)
        self.finished.emit(benchmark_results, total_score, total_wattage)

    def update_progress(self, value):
        self.progress_updated.emit(value)

    def emit_current_test_info(self, text):
        self.current_test_info.emit(text)


"""
Performs a GPU benchmark by running matrix multiplication, elementwise multiplication, convolution, and custom operation
benchmarks concurrently using a ThreadPoolExecutor. The results are formatted as a dictionary of scores and a total score
is calculated by summing the individual scores. The wattage used during the benchmark is also measured.

Args:
    benchmark_worker (QThread): The QThread object used to update the progress of the benchmark.

Returns:
    tuple: A tuple containing the benchmark results as a dictionary, the total score as a formatted float, and the
    wattage used during the benchmark as a float.
"""
def perform_gpu_benchmark(benchmark_worker):
    start_wattage = measure_wattage()

    benchmark_results = {}

    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Matrix Multiply Benchmark
        matrix_multiply_future = executor.submit(run_matrix_multiply_benchmark, benchmark_worker)
        # Elementwise Multiply Benchmark
        elementwise_multiply_future = executor.submit(run_elementwise_multiply_benchmark, benchmark_worker)
        # Convolution Benchmark
        convolution_future = executor.submit(run_convolution_benchmark, benchmark_worker)
        # Custom Operation Benchmark
        custom_operation_future = executor.submit(run_custom_operation_benchmark, benchmark_worker)

        benchmark_results['matrix_multiply'] = format_score(matrix_multiply_future.result())
        benchmark_results['elementwise_multiply'] = format_score(elementwise_multiply_future.result())
        benchmark_results['convolution'] = format_score(convolution_future.result())
        benchmark_results['custom_operation'] = format_score(custom_operation_future.result())

    print("All Benchmarks Finished")

    total_score = sum(benchmark_results.values())

    end_wattage = measure_wattage()
    total_wattage = end_wattage - start_wattage

    return benchmark_results, format_score(total_score), total_wattage


"""
Formats the given score as a positive float with 3 decimal places.

Args:
    score (float): The score to format.

Returns:
    float: The formatted score as a positive float with 3 decimal places.
"""
def format_score(score):
    formatted_score = max(0, float("{:.3f}".format(score)))
    return formatted_score



"""
Performs a matrix multiplication benchmark by generating two random matrices of size matrix_size x matrix_size and
multiplying them together using TensorFlow's matrix multiplication function. The benchmark is repeated iterations times
and the average score is calculated by taking the mean of the scores from each iteration. The progress of the benchmark is
updated using the given benchmark_worker object.

Args:
    benchmark_worker (QThread): The QThread object used to update the progress of the benchmark.

Returns:
    float: The average score of the matrix multiplication benchmark.
"""
def run_matrix_multiply_benchmark(benchmark_worker):
    # Perform a matrix multiplication benchmark
    matrix_size = 1000
    iterations = 1000 

    scores = []
    for _ in range(iterations):
        matrix_a = tf.random.normal((matrix_size, matrix_size))
        matrix_b = tf.random.normal((matrix_size, matrix_size))
        result = tf.linalg.matmul(matrix_a, matrix_b)
        score = tf.reduce_mean(result)
        scores.append(score)

    average_score = tf.reduce_mean(scores)

    for i in range(0, 101, 10):
        benchmark_worker.update_progress(i)
        benchmark_worker.emit_current_test_info("Matrix Multiply Benchmark Progress: {}%".format(i))
        QThread.msleep(100)

    return average_score




"""
Performs an elementwise multiplication benchmark by generating two random vectors of size vector_size and multiplying
them elementwise using TensorFlow's elementwise multiplication function. The benchmark is repeated iterations times and
the average score is calculated by taking the mean of the scores from each iteration. The progress of the benchmark is
updated using the given benchmark_worker object.

Args:
    benchmark_worker (QThread): The QThread object used to update the progress of the benchmark.

Returns:
    float: The average score of the elementwise multiplication benchmark.
"""
def run_elementwise_multiply_benchmark(benchmark_worker):
    # Perform an elementwise multiplication benchmark
    vector_size = 1000
    iterations = 10000 

    scores = []
    for _ in range(iterations):
        vector_a = tf.random.normal((vector_size,))
        vector_b = tf.random.normal((vector_size,))
        result = tf.multiply(vector_a, vector_b)
        score = tf.reduce_mean(result)
        scores.append(score)

    average_score = tf.reduce_mean(scores)

    for i in range(0, 101, 10):
        benchmark_worker.update_progress(i)
        benchmark_worker.emit_current_test_info("Elementwise Multiply Benchmark Progress: {}%".format(i))
        QThread.msleep(100)

    return average_score



"""
Performs a convolution benchmark by generating a random image and kernel, and applying the convolution operation using
TensorFlow's convolution function. The benchmark is repeated iterations times and the average score is calculated by
taking the mean of the scores from each iteration. The progress of the benchmark is updated using the given
benchmark_worker object, I had to reseearch this alot as this was very difficult to understand and implement with code.

Args:
    benchmark_worker (QThread): The QThread object used to update the progress of the benchmark.

Returns:
    float: The average score of the convolution benchmark.
"""
def run_convolution_benchmark(benchmark_worker):
    # Perform a convolution benchmark
    image_size = 100
    kernel_size = 3
    iterations = 1000

    scores = []
    for _ in range(iterations):
        image = tf.random.normal((1, image_size, image_size, 3))
        kernel = tf.random.normal((kernel_size, kernel_size, 3, 64))
        result = tf.nn.conv2d(image, kernel, strides=(1, 1), padding='SAME')
        score = tf.reduce_mean(result)
        scores.append(score)

    average_score = tf.reduce_mean(scores)

    for i in range(0, 101, 10):
        benchmark_worker.update_progress(i)
        benchmark_worker.emit_current_test_info("Convolution Benchmark Progress: {}%".format(i))
        QThread.msleep(100)

    return average_score


"""
Performs a custom GPU operation benchmark by generating a random input data and weights, and applying a custom
operation using TensorFlow's reduce_sum, square, and multiply functions. The benchmark is repeated iterations times
and the average score is calculated by taking the mean of the scores from each iteration. The progress of the benchmark
is updated using the given benchmark_worker object.

Args:
    benchmark_worker (QThread): The QThread object used to update the progress of the benchmark.

Returns:
    float: The average score of the custom operation benchmark.
"""
def run_custom_operation_benchmark(benchmark_worker):
    input_size = 1000
    iterations = 10000 

    scores = []
    for _ in range(iterations):
        input_data = tf.random.normal((input_size,))
        weights = tf.random.normal((input_size,))
        result = tf.reduce_sum(tf.square(tf.multiply(input_data, weights)))
        score = tf.reduce_mean(result)
        scores.append(score)

    average_score = tf.reduce_mean(scores)

    for i in range(0, 101, 10):
        benchmark_worker.update_progress(i)
        benchmark_worker.emit_current_test_info("Custom Operation Benchmark Progress: {}%".format(i))
        QThread.msleep(100)

    return average_score
