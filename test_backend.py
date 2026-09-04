import json
import random
import time
import psycopg2
from psycopg2 import sql
from statistics import mean, median, stdev

# Setup test environment with virtual environment
# Run: python -m venv venv
# Activate: source venv/bin/activate on Unix or venv\Scripts\activate on Windows
# Install dependencies: pip install psycopg2-binary

# Database connection parameters
DB_HOST = 'localhost'
DB_NAME = 'testdb'
DB_USER = 'testuser'
DB_PASSWORD = 'testpassword'

# Create test script to measure database latency
def measure_latency():
    conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    cur = conn.cursor()
    latency_data = []
    
    for _ in range(100):
        start_time = time.time()
        cur.execute(sql.SQL("SELECT 1"))
        end_time = time.time()
        latency = end_time - start_time
        latency_data.append(latency)
    
    cur.close()
    conn.close()
    return latency_data

# Run multiple stress tests with a large number of queries
def run_stress_test(num_queries):
    conn = psycopg2.connect(host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    cur = conn.cursor()
    
    for _ in range(num_queries):
        cur.execute(sql.SQL("INSERT INTO test_table (value) VALUES (%s)"), (random.randint(1, 100),))
    
    cur.close()
    conn.close()

# Collect and store latency data in JSON
def collect_latency_data(num_queries):
    latency_data = measure_latency()
    run_stress_test(num_queries)
    new_latency_data = measure_latency()
    all_latency_data = latency_data + new_latency_data
    with open('latency_data.json', 'w') as f:
        json.dump(all_latency_data, f)

# Analyze data to determine mean, median, and standard deviation
def analyze_latency_data():
    with open('latency_data.json', 'r') as f:
        latency_data = json.load(f)
    mean_latency = mean(latency_data)
    median_latency = median(latency_data)
    std_dev_latency = stdev(latency_data)
    return mean_latency, median_latency, std_dev_latency

# Compare results with documented targets
def compare_results(mean_latency, median_latency, std_dev_latency):
    target_mean = 0.01
    target_median = 0.01
    target_std_dev = 0.005
    results = {
        'mean': {'actual': mean_latency, 'target': target_mean, 'within_target': mean_latency <= target_mean},
        'median': {'actual': median_latency, 'target': target_median, 'within_target': median_latency <= target_median},
        'std_dev': {'actual': std_dev_latency, 'target': target_std_dev, 'within_target': std_dev_latency <= target_std_dev}
    }
    return results

# Investigate and address any performance issues
def investigate_performance_issues(results):
    issues = []
    if not results['mean']['within_target']:
        issues.append('Mean latency exceeds target')
    if not results['median']['within_target']:
        issues.append('Median latency exceeds target')
    if not results['std_dev']['within_target']:
        issues.append('Standard deviation exceeds target')
    return issues

# Document findings and recommendations
def document_findings_and_recommendations(issues):
    with open('performance_report.txt', 'w') as f:
        f.write('Performance Report\n')
        f.write('-----------------\n')
        f.write('Issues:\n')
        for issue in issues:
            f.write(f'- {issue}\n')
        f.write('\nRecommendations:\n')
        if 'Mean latency exceeds target' in issues:
            f.write('- Optimize database queries\n')
        if 'Median latency exceeds target' in issues:
            f.write('- Use connection pooling\n')
        if 'Standard deviation exceeds target' in issues:
            f.write('- Identify and address bottlenecks\n')

# Main function to run the test
def main():
    num_queries = 1000
    collect_latency_data(num_queries)
    mean_latency, median_latency, std_dev_latency = analyze_latency_data()
    results = compare_results(mean_latency, median_latency, std_dev_latency)
    issues = investigate_performance_issues(results)
    document_findings_and_recommendations(issues)

if __name__ == '__main__':
    main()