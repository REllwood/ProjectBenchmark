from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QProgressBar, QTabWidget
from PyQt6.QtCore import QThread, pyqtSignal
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

from cpuBenchmark import perform_cpu_benchmark
from gpuBenchmark import perform_gpu_benchmark
from ramBenchmark import perform_ram_benchmark
from ssdBenchmark import perform_ssd_benchmark
from neBenchmark import perform_neural_engine_benchmark
from wattage import measure_wattage


class BenchmarkWorker(QThread):
    benchmark_finished = pyqtSignal(dict, float, float)
    progress_update = pyqtSignal(int)
    current_test_info = pyqtSignal(str)

    def __init__(self, benchmark_fn, test_name):
        super().__init__()
        self.benchmark_fn = benchmark_fn
        self.test_name = test_name
        self.progress = 0

   
    def run(self):
        print("Benchmark started:", self.test_name)
        benchmark_results, total_score, total_wattage = self.benchmark_fn(self)
        print("Benchmark finished:", self.test_name)
        self.benchmark_finished.emit(benchmark_results, total_score, total_wattage)

   
    """
    Updates the progress of the benchmark and emits a signal with the updated progress.

    :param progress: An integer representing the progress of the benchmark.
    """
    def update_progress(self, progress):
        self.progress = progress
        self.progress_update.emit(progress)

   
    """
    Emits a signal with the current test information.

    :param test_info: A string containing the current test information.
    """
    def emit_current_test_info(self, test_info):
        self.current_test_info.emit(test_info)

    "I feel like this is self explanatory"
    def stop(self):
        self.terminate()


class BenchmarkWidget(QWidget):
    benchmark_finished = pyqtSignal(dict, float, float)

    def __init__(self, benchmark_fn, label_text):
        super().__init__()

        self.benchmark_fn = benchmark_fn
        self.label_text = label_text

        self.current_test_label = QLabel("Current Test: ")
        self.progress_bar = QProgressBar()
        self.progress_label = QLabel("0%")
        self.score_label = QLabel("Score: N/A")
        self.wattage_label = QLabel("Wattage: N/A")

        self.fig = plt.Figure(figsize=(5, 4), dpi=100)
        self.graph = self.fig.add_subplot(111)
        self.graph.set_title("Benchmark Results")
        self.graph.set_xlabel("Run")
        self.graph.set_ylabel("Score")
        self.graph.grid()

        self.canvas = FigureCanvas(self.fig)

        self.run_button = QPushButton("Run Benchmark")
        self.run_button.clicked.connect(self.run_benchmark)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(QLabel(self.label_text))
        self.layout.addWidget(self.current_test_label)
        self.layout.addWidget(self.progress_bar)
        self.layout.addWidget(self.progress_label)
        self.layout.addWidget(self.score_label)
        self.layout.addWidget(self.wattage_label)
        self.layout.addWidget(self.canvas)
        self.layout.addWidget(self.run_button)

        self.benchmark_worker = None
        self.run_count = 0
        self.scores = []


    """
    Runs the benchmark by creating a new BenchmarkWorker thread and connecting its signals to the appropriate
    slots. The run button is disabled while the benchmark is running, and the progress bar and progress label are
    reset to 0. Once the benchmark is finished, the handle_benchmark_finished method is called to handle the
    results. The benchmark score is stored and the graph is updated with the latest score.
    """
    def run_benchmark(self):
        self.run_button.setEnabled(False)
        self.run_button.setText("Running...")
        self.progress_bar.setValue(0)  # Reset progress bar
        self.progress_label.setText("0%")  # Reset progress label

        self.benchmark_worker = BenchmarkWorker(self.benchmark_fn, self.label_text)
        self.benchmark_worker.current_test_info.connect(self.current_test_label.setText)
        self.benchmark_worker.progress_update.connect(self.update_progress)
        self.benchmark_worker.benchmark_finished.connect(self.handle_benchmark_finished)

        self.benchmark_worker.start()



    """
    Handles the completion of a benchmark by enabling the run button, emitting the benchmark results signal, storing
    the benchmark score, and updating the graph with the latest score.

    Args:
        benchmark_results (dict): A dictionary containing the results of the benchmark.
        total_score (float): The total benchmark score.
        total_wattage (float): The total wattage used during the benchmark.

    Returns:
        None
    """
    def handle_benchmark_finished(self, benchmark_results, total_score, total_wattage):
        self.run_button.setEnabled(True)
        self.run_button.setText("Run Benchmark")
        self.benchmark_finished.emit(benchmark_results, total_score, total_wattage)

        # Store the score and update the graph
        self.scores.append(total_score)
        self.update_graph()



    """
    Updates the progress bar and progress label with the given progress value.

    Args:
        progress (int): The progress value to display on the progress bar and progress label.

    Returns:
        None
    """
    def update_progress(self, progress):
        self.progress_bar.setValue(progress)
        self.progress_label.setText(f"{progress}%")

    """
    Updates the graph with the latest benchmark score.

    The graph displays the benchmark score for each run of the benchmark. The x-axis represents the run number, and
    the y-axis represents the benchmark score. The graph is updated every time a new benchmark is run.

    Returns:
        None
    """
    def update_graph(self):
            self.graph.clear()

            runs = range(1, len(self.scores) + 1)
            self.graph.plot(runs, self.scores, marker='o')
            self.graph.set_title("Benchmark Results")
            self.graph.set_xlabel("Run")
            self.graph.set_ylabel("Score")
            self.graph.grid()

            self.canvas.draw()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Apple System Benchmark")
        self.total_score = 0
        self.total_wattage = 0

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.create_widgets()


    """
    Creates the widgets for the main window, including the tab widget for each benchmark type and the labels for the
    total score and total wattage.
    """
    def create_widgets(self):
        tab_widget = QTabWidget()
        self.layout.addWidget(tab_widget)

        # CPU Benchmark
        cpu_widget = BenchmarkWidget(perform_cpu_benchmark, "CPU Benchmark")
        cpu_widget.benchmark_finished.connect(self.update_results)
        tab_widget.addTab(cpu_widget, "CPU")

        # GPU Benchmark
        gpu_widget = BenchmarkWidget(perform_gpu_benchmark, "GPU Benchmark")
        gpu_widget.benchmark_finished.connect(self.update_results)
        tab_widget.addTab(gpu_widget, "GPU")

        # RAM Benchmark
        ram_widget = BenchmarkWidget(perform_ram_benchmark, "RAM Benchmark")
        ram_widget.benchmark_finished.connect(self.update_results)
        tab_widget.addTab(ram_widget, "RAM")

        # SSD Benchmark
        ssd_widget = BenchmarkWidget(perform_ssd_benchmark, "SSD Benchmark")
        ssd_widget.benchmark_finished.connect(self.update_results)
        tab_widget.addTab(ssd_widget, "SSD")

        # Neural Engine Benchmark
        neural_widget = BenchmarkWidget(perform_neural_engine_benchmark, "Neural Engine Benchmark")
        neural_widget.benchmark_finished.connect(self.update_results)
        tab_widget.addTab(neural_widget, "Neural Engine")

        self.layout.addStretch()

        # Total Score Label
        self.total_score_label = QLabel("Total Score: 0.000")
        self.layout.addWidget(self.total_score_label)

        # Total Wattage Label
        self.total_wattage_label = QLabel("Total Wattage: 0")
        self.layout.addWidget(self.total_wattage_label)

    
    
    """
    Updates the total score and total wattage labels with the given benchmark results, total score, and total wattage.

    Args:
        benchmark_results (dict): A dictionary containing the individual scores for each test.
        total_score (float): The total score for all tests.
        total_wattage (float): The total wattage for all tests.
    """
    def update_results(self, benchmark_results, total_score, total_wattage):
        if benchmark_results:
            individual_scores = benchmark_results
            self.total_score += total_score
            self.total_wattage += total_wattage

            # Update score and wattage labels
            self.total_score_label.setText("Total Score: {:.3f}".format(self.total_score))
            self.total_wattage_label.setText("Total Wattage: {}".format(self.total_wattage))
        else:
            self.total_score_label.setText("Total Score: N/A")
            self.total_wattage_label.setText("Total Wattage: N/A")



    """
    Overrides the default close event for the main window.

    This method is called when the user clicks the close button on the main window. It stops any running benchmarks
    before closing the window.

    Args:
        event (QCloseEvent): The close event.

    Returns:
        None
    """
    def closeEvent(self, event):
        # Stop any running benchmarks
        for widget in self.central_widget.findChildren(BenchmarkWidget):
            if widget.benchmark_worker and widget.benchmark_worker.isRunning():
                widget.benchmark_worker.stop()
        event.accept()


if __name__ == '__main__':
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
