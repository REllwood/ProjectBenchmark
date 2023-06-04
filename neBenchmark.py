import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
import concurrent.futures
from wattage import measure_wattage
import tensorflow as tf


class BenchmarkWorker(QThread):
    progress_updated = pyqtSignal(int)
    current_test_info = pyqtSignal(str)

    def run(self):
        benchmark_results, total_score, total_wattage = perform_neural_engine_benchmark(self)
        self.finished.emit(benchmark_results, total_score, total_wattage)

    def update_progress(self, value):
        self.progress_updated.emit(value)

    def emit_current_test_info(self, text):
        self.current_test_info.emit(text)




"""
Runs the Neural Engine benchmarks concurrently and returns the benchmark results, total score, and total wattage.

Args:
    benchmark_worker (BenchmarkWorker): The worker thread object to update the progress and current test info.

Returns:
    tuple: A tuple containing the benchmark results, total score, and total wattage.
"""
def perform_neural_engine_benchmark(benchmark_worker):

    start_wattage = measure_wattage()

    # Run the Neural Engine benchmarks concurrently
    benchmark_results = {}

    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Neural Network Inference Benchmark
        inference_future = executor.submit(run_neural_network_inference_benchmark, benchmark_worker)
        # Neural Network Training Benchmark
        training_future = executor.submit(run_neural_network_training_benchmark, benchmark_worker)

        benchmark_results['inference'] = inference_future.result()
        benchmark_results['training'] = training_future.result()

    print("All Neural Engine Benchmarks Finished")

    total_score = sum(benchmark_results.values())

    end_wattage = measure_wattage()
    total_wattage = end_wattage - start_wattage

    return benchmark_results, total_score, total_wattage




"""
Performs a Neural Network inference benchmark.

Args:
    benchmark_worker (BenchmarkWorker): The worker thread object to update the progress and current test info.

Returns:
    float: The average score of the benchmark.
"""
def run_neural_network_inference_benchmark(benchmark_worker):
    model = tf.keras.applications.MobileNetV2(weights='imagenet')
    image = tf.random.normal((1, 224, 224, 3))

    scores = []
    for _ in range(1000):
        prediction = model.predict(image)
        scores.append(np.max(prediction))

    average_score = np.mean(scores)

    for i in range(0, 101, 10):
        benchmark_worker.update_progress(i)
        benchmark_worker.emit_current_test_info("Neural Network Inference Benchmark Progress: {}%".format(i))
        QThread.msleep(100)

    return average_score





"""
Performs a Neural Network training benchmark.

Args:
    benchmark_worker (BenchmarkWorker): The worker thread object to update the progress and current test info.

Returns:
    float: The average score of the benchmark.
"""        
def run_neural_network_training_benchmark(benchmark_worker):
    # Perform a Neural Network training benchmark
    model = tf.keras.applications.MobileNetV2(weights=None)
    images = tf.random.normal((1000, 224, 224, 3))
    labels = tf.random.uniform((1000,), minval=0, maxval=1000, dtype=tf.int32)

    model.compile(optimizer='adam', loss='sparse_categorical_crossentropy', metrics=['accuracy'])

    for _ in range(10): 
        model.fit(images, labels, epochs=1, batch_size=32, verbose=0)

    score = model.evaluate(images, labels)[1]

    for i in range(0, 101, 10):
        benchmark_worker.update_progress(i)
        benchmark_worker.emit_current_test_info("Neural Network Training Benchmark Progress: {}%".format(i))
        QThread.msleep(100)

    return score
