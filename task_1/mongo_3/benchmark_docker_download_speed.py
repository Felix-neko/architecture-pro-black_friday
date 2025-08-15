import subprocess
import time
import json
from pathlib import Path

def benchmark_docker_pull(image, runs=3):
    """Benchmark Docker pull speed in MB/s"""
    results = []

    for i in range(runs):
        # Remove image to force full download
        subprocess.run(['docker', 'rmi', image],
                       capture_output=True, check=False)

        # Measure pull time
        start_time = time.time()
        result = subprocess.run(['docker', 'pull', image],
                                capture_output=True, text=True)
        end_time = time.time()

        if result.returncode == 0:
            # Get image size
            inspect = subprocess.run(['docker', 'image', 'inspect', image],
                                     capture_output=True, text=True)
            size_bytes = json.loads(inspect.stdout)[0]['Size']
            size_mb = size_bytes / (1024 * 1024)

            download_time = end_time - start_time
            speed_mbps = size_mb / download_time

            results.append({
                'run': i + 1,
                'size_mb': round(size_mb, 2),
                'time_sec': round(download_time, 2),
                'speed_mbps': round(speed_mbps, 2)
            })

            print(f"Run {i+1}: {size_mb:.1f} MB in {download_time:.1f}s = {speed_mbps:.1f} MB/s")

    return results

# Example usage
if __name__ == "__main__":
    images = ['nginx:latest', 'python:3.11-slim', 'alpine:latest']

    for image in images:
        print(f"\nBenchmarking {image}:")
        results = benchmark_docker_pull(image, runs=3)

        if results:
            avg_speed = sum(r['speed_mbps'] for r in results) / len(results)
            print(f"Average speed: {avg_speed:.1f} MB/s")