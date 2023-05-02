from typing import List, Optional
from dataclasses import dataclass, field
from contextlib import contextmanager
from logging import getLogger

from pandas import DataFrame
import torch
import time

LOGGER = getLogger("benchmark")


@dataclass
class Benchmark:
    latencies: List[float] = field(default_factory=list)
    throughput: Optional[float] = float('-inf')

    @property
    def num_runs(self) -> int:
        return len(self.latencies)

    @property
    def runs_duration(self) -> float:
        return sum(self.latencies)

    @property
    def perfs(self) -> DataFrame:
        return DataFrame({
            "mean_latency": self.runs_duration / self.num_runs,
            "throughput": self.throughput
        }, index=[0])

    @property
    def details(self) -> DataFrame:
        return DataFrame({
            "latencies": self.latencies,
        }, index=range(self.num_runs))

    @contextmanager
    def track(self, device: str):
        if device == "cpu":
            start = time.perf_counter_ns()
            yield
            end = time.perf_counter_ns()

            latency_ns = end - start
            latency = latency_ns / 1e9

            self.latencies.append(latency)

            LOGGER.debug(
                f'Tracked CPU latency took: {latency}s)')
        
        elif device == "cuda":
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)

            start_event.record()
            yield
            end_event.record()

            torch.cuda.synchronize()
            
            latency_ms = start_event.elapsed_time(end_event)
            latency = latency_ms / 1e3

            self.latencies.append(latency)

            LOGGER.debug(
                f'Tracked CUDA latency took: {latency}s)')
        else:
            raise ValueError(
                f"Unsupported device type {device}")

    def finalize(self, benchmark_duration: int):
        self.throughput = self.num_runs / benchmark_duration

    @staticmethod
    def merge(benchmarks: List['Benchmark']) -> 'Benchmark':
        latencies, throughputs = [], []

        for b in benchmarks:

            assert len(b.latencies) > 0, \
                "Empty benchmark (0 latency measurements recorded)"
            assert b.throughput > 0., \
                f"Benchmark has not been finalized, throughput < 0 ({b.throughput})"

            latencies += b.latencies
            throughputs.append(b.throughput)

        # Return all the latencies measured and the mean throughput over all instances
        mean_throughput = sum(throughputs) / len(throughputs)

        return Benchmark(
            latencies,
            mean_throughput
        )
