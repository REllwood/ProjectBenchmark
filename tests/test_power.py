from asbench.core.power import POWERMETRICS_ARGS, PowermetricsParser, PowerSample, summarise, sudoers_rule

APPLE_SILICON = """\
Machine model: Mac14,9
OS version: 23F79

*** Sampled system activity (Tue Sep 29 15:04:00 2026 +1000) (502.31ms elapsed) ***

**** Processor usage ****

E-Cluster HW active frequency: 1107 MHz
P0-Cluster HW active residency:  88.21%
CPU Power: 4210 mW
GPU Power: 120 mW
ANE Power: 0 mW
Combined Power (CPU + GPU + ANE): 4330 mW

**** GPU usage ****

GPU HW active frequency: 444 MHz
GPU Power: 120 mW

**** Thermal pressure ****

Current pressure level: Nominal

*** Sampled system activity (Tue Sep 29 15:04:00 2026 +1000) (500.02ms elapsed) ***

**** Processor usage ****

CPU Power: 5800 mW
GPU Power: 150 mW
ANE Power: 50 mW
Combined Power (CPU + GPU + ANE): 6000 mW

**** Thermal pressure ****

Current pressure level: Moderate
"""


def parse(text):
    parser = PowermetricsParser()
    samples = [s for line in text.splitlines() if (s := parser.feed(line))]
    if last := parser.flush():
        samples.append(last)
    return samples


def test_parses_apple_silicon_samples_in_watts():
    first, second = parse(APPLE_SILICON)
    assert (first.cpu_w, first.gpu_w, first.ane_w, first.combined_w) == (4.21, 0.12, 0.0, 4.33)
    assert first.thermal == "Nominal"
    assert second.combined_w == 6.0 and second.ane_w == 0.05 and second.thermal == "Moderate"


def test_parses_intel_package_power():
    text = "*** Sampled system activity ***\nIntel energy model derived package power (CPUs+GT+SA): 1.48W\n"
    (sample,) = parse(text)
    assert sample.combined_w == 1.48


def test_total_falls_back_to_sum_of_parts():
    assert PowerSample(t=0, cpu_w=2.0, gpu_w=0.5).total_w == 2.5


def test_summary_averages_and_keeps_worst_thermal_level():
    summary = summarise(parse(APPLE_SILICON), duration=10.0)
    assert summary.available and summary.samples == 2
    assert summary.avg_w == 5.165 and summary.peak_w == 6.0
    assert summary.energy_j == 51.65
    assert summary.thermal == "Moderate"


def test_summary_without_samples_is_unavailable():
    assert not summarise([], duration=5).available


def test_sudoers_rule_allows_exactly_our_command():
    rule = sudoers_rule("alex")
    assert rule.startswith("alex ALL=(root) NOPASSWD: /usr/bin/powermetrics ")
    assert "cpu_power\\,gpu_power\\,thermal" in rule  # commas must be escaped in sudoers
    assert "-o" not in POWERMETRICS_ARGS  # writing files as root must not be possible
    assert "-n" in POWERMETRICS_ARGS  # powermetrics must stop by itself eventually
